import logging
import sys
import time
from datetime import datetime, timezone
from urllib.parse import quote

import psycopg
import requests

from config import (
    DB_URL,
    MATCH_COUNT,
    RANKED_SOLO_QUEUE,
    RANKED_SOLO_QUEUE_TYPE,
    RIOT_BASE_URL,
    RIOT_PLATFORM_URL,
    required_env,
)

# El formato lo configura config.py, que se importa antes
log = logging.getLogger("collector")

# Se leen aquí y no en config.py porque solo las usa el collector. Así la API
# y los tests pueden importar config.py sin tener las variables de Riot.
RIOT_API_KEY = required_env("RIOT_API_KEY")
RIOT_GAME_NAME = required_env("RIOT_GAME_NAME")
RIOT_TAG_LINE = required_env("RIOT_TAG_LINE")

# Con --refetch se vuelven a pedir a Riot las partidas ya guardadas, para
# rellenar columnas añadidas después. Sin él, las que ya están se saltan.
refetch = "--refetch" in sys.argv

# En estos rangos se sube por plazas. Cada día Riot ordena a todos los jugadores
# desde Master, y en EUW los 300 primeros son Challenger y los 700 siguientes GM
APEX_LEAGUES = ["challengerleagues", "grandmasterleagues", "masterleagues"]

# Para cada rango, el puesto que ocupa la última plaza del siguiente y el mínimo
# de LP que pide Riot para entrar
NEXT_APEX_CUTOFF = {
    "MASTER": (1000, 200),
    "GRANDMASTER": (300, 500),
}


def fetch(url, params=None, attempts=3):
    for attempt in range(attempts):
        try:
            response = requests.get(
                url,
                headers={"X-Riot-Token": RIOT_API_KEY},
                params=params,
                # Sin timeout, una petición que Riot acepta pero no contesta
                # deja el proceso esperando para siempre, sin error ni log.
                timeout=15,
            )
        except requests.exceptions.RequestException as error:
            delay = 2**attempt
            log.warning(
                "Fallo de red (%s), reintento en %ss", error.__class__.__name__, delay
            )
            time.sleep(delay)
            continue

        if response.status_code == 429:
            delay = int(response.headers.get("Retry-After", 10))
            log.warning("Límite alcanzado, esperando %ss", delay)
            time.sleep(delay)
            continue

        # Los 5xx suelen ser temporales, así que se reintenta
        if response.status_code >= 500:
            delay = 2**attempt
            log.warning(
                "Riot devolvió %s, reintento en %ss", response.status_code, delay
            )
            time.sleep(delay)
            continue

        return response

    return None


def save_timeline(cursor, match_id):
    """Descarga el timeline de una partida y guarda compras y habilidades.

    Es una petición extra por partida, porque el detalle y el timeline son dos
    endpoints distintos. Devuelve cuántas filas ha guardado de cada cosa.
    """
    response = fetch(f"{RIOT_BASE_URL}/lol/match/v5/matches/{match_id}/timeline")

    if response is None or response.status_code != 200:
        raise RuntimeError(f"Sin timeline para {match_id}")

    purchases = []
    level_ups = []

    for frame in response.json()["info"]["frames"]:
        for event in frame["events"]:
            # El participante 0 no existe. Son artefactos del arranque
            participant_id = event.get("participantId", 0)
            if participant_id < 1:
                continue

            event_type = event["type"]

            if event_type == "ITEM_PURCHASED":
                purchases.append(
                    [match_id, participant_id, event["itemId"], event["timestamp"]]
                )

            elif event_type == "ITEM_UNDO" and event["afterId"] == 0:
                # Se quita la última compra del objeto, porque no llegó a ocurrir. Un
                # afterId distinto de 0 deshace una venta, que aquí no cuenta.
                for i in range(len(purchases) - 1, -1, -1):
                    if (
                        purchases[i][1] == participant_id
                        and purchases[i][2] == event["beforeId"]
                    ):
                        del purchases[i]
                        break

            elif event_type == "SKILL_LEVEL_UP":
                level_ups.append(
                    [
                        match_id,
                        participant_id,
                        event["skillSlot"],
                        event["levelUpType"],
                        event["timestamp"],
                    ]
                )

    # Con --refetch la partida puede tener filas de una ejecución anterior. Como
    # la clave es un id automático, insertar sin más las duplicaría.
    cursor.execute("DELETE FROM item_purchases WHERE match_id = %s", (match_id,))
    cursor.execute("DELETE FROM skill_levelups WHERE match_id = %s", (match_id,))

    cursor.executemany(
        """
        INSERT INTO item_purchases (match_id, participant_id, item_id, timestamp_ms)
        VALUES (%s, %s, %s, %s)
        """,
        purchases,
    )
    cursor.executemany(
        """
        INSERT INTO skill_levelups
            (match_id, participant_id, skill_slot, level_up_type, timestamp_ms)
        VALUES (%s, %s, %s, %s, %s)
        """,
        level_ups,
    )

    return len(purchases), len(level_ups)


def runes(participant):
    """Devuelve los dos árboles, las seis runas y los tres fragmentos.

    Riot da un árbol con la descripción primaryStyle y otro con subStyle, cada
    uno con sus runas en orden. Lo que no venga se devuelve como None.
    """
    perks = participant.get("perks", {})
    styles = {style["description"]: style for style in perks.get("styles", [])}
    primary = styles.get("primaryStyle")
    secondary = styles.get("subStyle")

    rune_ids = None
    if primary and secondary:
        selections = primary["selections"] + secondary["selections"]
        rune_ids = [selection["perk"] for selection in selections]

    stats = perks.get("statPerks")
    shard_ids = [stats["offense"], stats["flex"], stats["defense"]] if stats else None

    return (
        primary["style"] if primary else None,
        secondary["style"] if secondary else None,
        rune_ids,
        shard_ids,
    )


def solo_entry(entries):
    """De las entradas de LEAGUE-V4 de un jugador, la de Solo/Duo o None.

    Riot devuelve una entrada por cola, también la de Flex.
    """
    return next((e for e in entries if e["queueType"] == RANKED_SOLO_QUEUE_TYPE), None)


def solo_rank(player_puuid, cache):
    """Devuelve la entrada de Solo/Duo de un jugador de la partida, o None.

    Se apunta en cache, porque el mismo jugador puede salir en varias partidas
    de la misma ejecución, como un compañero de dúo. Si la petición falla no se
    apunta, y la partida se guarda igual con el rango vacío.
    """
    if player_puuid in cache:
        return cache[player_puuid]

    response = fetch(
        f"{RIOT_PLATFORM_URL}/lol/league/v4/entries/by-puuid/{player_puuid}"
    )
    if response is None or response.status_code != 200:
        log.warning("Sin rango de un jugador, se guarda vacío")
        return None

    cache[player_puuid] = solo_entry(response.json())
    return cache[player_puuid]


def save_ranked(cursor, puuid):
    """Guarda un snapshot de la clasificatoria de Solo/Duo del invocador.

    Devuelve la entrada de Riot y el corte, o None si no tiene clasificatoria.
    """
    response = fetch(f"{RIOT_PLATFORM_URL}/lol/league/v4/entries/by-puuid/{puuid}")

    if response is None or response.status_code != 200:
        raise RuntimeError("Sin respuesta de LEAGUE-V4")

    solo = solo_entry(response.json())
    if solo is None:
        return None

    cutoff = None
    apex = NEXT_APEX_CUTOFF.get(solo["tier"])
    if apex:
        position, minimum = apex
        everyone = []
        for league in APEX_LEAGUES:
            league_response = fetch(
                f"{RIOT_PLATFORM_URL}/lol/league/v4/{league}/by-queue/"
                f"{RANKED_SOLO_QUEUE_TYPE}"
            )
            if league_response is None or league_response.status_code != 200:
                raise RuntimeError(f"Sin la lista de {league}")
            everyone += [e["leaguePoints"] for e in league_response.json()["entries"]]

        # Hay que superar al que ocupa la última plaza, así que se suma 1. Si no
        # hay tanta gente, como a principio de temporada, basta con el mínimo
        everyone.sort(reverse=True)
        cutoff = minimum
        if len(everyone) >= position:
            cutoff = max(minimum, everyone[position - 1] + 1)

    cursor.execute(
        """
        INSERT INTO ranked_snapshots
            (puuid, tier, division, league_points, wins, losses, next_cutoff_lp)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (
            puuid,
            solo["tier"],
            solo["rank"],
            solo["leaguePoints"],
            solo["wins"],
            solo["losses"],
            cutoff,
        ),
    )

    return solo, cutoff


log.info("Consultando datos de %s#%s", RIOT_GAME_NAME, RIOT_TAG_LINE)

account_response = fetch(
    f"{RIOT_BASE_URL}/riot/account/v1/accounts/by-riot-id/"
    f"{quote(RIOT_GAME_NAME)}/{RIOT_TAG_LINE}"
)

if account_response is None:
    log.error("No se ha podido conectar con la API de Riot tras varios intentos")
    sys.exit(1)

if account_response.status_code != 200:
    meanings = {
        401: "no autorizado",
        403: "prohibido",
        404: "no encontrado",
        429: "demasiadas peticiones",
        500: "error interno del servidor",
        503: "servicio no disponible",
    }
    meaning = meanings.get(account_response.status_code, "error desconocido")
    log.error(
        "Error al obtener la cuenta: %s (%s)", account_response.status_code, meaning
    )

    if account_response.status_code in (401, 403):
        log.error("La clave no es válida. Revísala en developer.riotgames.com")
    sys.exit(1)

puuid = account_response.json()["puuid"]

# El icono y el nivel están en otra API, SUMMONER-V4. Si falla, el invocador
# se guarda igual y conserva los que tenía.
summoner_response = fetch(
    f"{RIOT_PLATFORM_URL}/lol/summoner/v4/summoners/by-puuid/{puuid}"
)
if summoner_response is not None and summoner_response.status_code == 200:
    summoner = summoner_response.json()
    profile_icon_id = summoner["profileIconId"]
    summoner_level = summoner["summonerLevel"]
else:
    log.warning("Sin icono ni nivel de SUMMONER-V4")
    profile_icon_id = None
    summoner_level = None

# Sin el filtro de cola Riot devuelve las últimas partidas de cualquier
# modo, y las normales y los swiftplay acabarían mezclados con las ranked.
ids_response = fetch(
    f"{RIOT_BASE_URL}/lol/match/v5/matches/by-puuid/{puuid}/ids",
    params={"count": MATCH_COUNT, "queue": RANKED_SOLO_QUEUE},
)

if ids_response is None or ids_response.status_code != 200:
    log.error("No se ha podido obtener la lista de partidas")
    sys.exit(1)

match_ids = ids_response.json()

log.info("Partidas encontradas: %s", len(match_ids))

saved = 0

# Rango de Solo/Duo de cada jugador ya consultado en esta ejecución, por PUUID.
# Vive solo mientras corre el collector, no se guarda en ningún sitio
rank_cache = {}

with (
    psycopg.connect(DB_URL) as connection,
    connection.cursor() as cursor,
):
    # El invocador va primero porque las participaciones lo referencian
    cursor.execute(
        """
        INSERT INTO summoners
            (puuid, game_name, tag_line, profile_icon_id, summoner_level)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (puuid) DO UPDATE SET
            game_name       = EXCLUDED.game_name,
            tag_line        = EXCLUDED.tag_line,
            -- Con NULL, porque SUMMONER-V4 falló, se queda el de la ejecución anterior
            profile_icon_id = COALESCE(EXCLUDED.profile_icon_id, summoners.profile_icon_id),
            summoner_level  = COALESCE(EXCLUDED.summoner_level, summoners.summoner_level)
        """,
        (puuid, RIOT_GAME_NAME, RIOT_TAG_LINE, profile_icon_id, summoner_level),
    )
    # Se confirma ya, para que la clasificatoria y las partidas lo encuentren
    # aunque uno de los dos falle
    connection.commit()

    # Si falla la clasificatoria, las partidas se guardan igual
    try:
        ranked = save_ranked(cursor, puuid)
        connection.commit()
    except Exception:
        connection.rollback()
        log.exception("Clasificatoria no guardada")
    else:
        # El rango del invocador ya está pedido, así que en las partidas no se repite
        rank_cache[puuid] = ranked[0] if ranked else None
        if ranked is None:
            log.info("Sin clasificatoria de Solo/Duo esta temporada")
        else:
            solo, cutoff = ranked
            log.info(
                "Clasificatoria: %s %s, %s LP, %sV %sD, corte %s",
                solo["tier"],
                solo["rank"],
                solo["leaguePoints"],
                solo["wins"],
                solo["losses"],
                cutoff,
            )

    # Cada partida se guarda entera en una transacción, así que basta con ver si
    # tiene compras. Mirando matches se saltarían las guardadas antes del timeline
    cursor.execute(
        """
        SELECT DISTINCT match_id FROM item_purchases WHERE match_id = ANY(%s)
        """,
        (match_ids,),
    )
    already_saved = {row[0] for row in cursor.fetchall()}

    if refetch:
        log.info(
            "Modo --refetch: se vuelven a pedir las %s guardadas", len(already_saved)
        )
        already_saved = set()
    elif already_saved:
        log.info("Ya guardadas, no se piden a Riot: %s", len(already_saved))

    for match_id in match_ids:
        if match_id in already_saved:
            continue

        try:
            match_response = fetch(f"{RIOT_BASE_URL}/lol/match/v5/matches/{match_id}")

            if match_response is None or match_response.status_code != 200:
                log.warning("No se ha podido descargar %s", match_id)
                continue

            info = match_response.json()["info"]

            # Riot da la fecha en milisegundos desde 1970
            played_at = datetime.fromtimestamp(
                info["gameCreation"] / 1000, timezone.utc
            )

            cursor.execute(
                """
                INSERT INTO matches
                    (match_id, played_at, duration_seconds, queue_id, game_version)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (match_id) DO UPDATE SET
                    played_at        = EXCLUDED.played_at,
                    duration_seconds = EXCLUDED.duration_seconds,
                    queue_id         = EXCLUDED.queue_id,
                    game_version     = EXCLUDED.game_version
                """,
                (
                    match_id,
                    played_at,
                    info["gameDuration"],
                    info["queueId"],
                    info["gameVersion"],
                ),
            )

            me = None

            for participant in info["participants"]:
                # Solo se guarda el PUUID de los invocadores seguidos. Del
                # resto basta el número de jugador, porque su identidad no hace falta.
                followed = participant["puuid"] == puuid
                if followed:
                    me = participant

                primary_style_id, secondary_style_id, rune_ids, shard_ids = runes(
                    participant
                )
                # Se pide con su PUUID, pero solo se guarda el rango, no quién es
                rank = solo_rank(participant["puuid"], rank_cache) or {}

                cursor.execute(
                    """
                    INSERT INTO participants
                        (match_id, puuid, champion, position, kills, deaths, assists, win,
                         damage_to_champions, damage_taken, gold_earned,
                         minions_killed, neutral_minions_killed,
                         vision_score, wards_placed,
                         item0, item1, item2, item3, item4, item5, item6,
                         summoner1_id, summoner2_id, participant_id, team_id,
                         champ_level, primary_style_id, secondary_style_id,
                         rune_ids, shard_ids, tier, division, league_points)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s,
                            %s, %s, %s,
                            %s, %s,
                            %s, %s,
                            %s, %s, %s, %s, %s, %s, %s,
                            %s, %s, %s, %s,
                            %s, %s, %s,
                            %s, %s, %s, %s, %s)
                    ON CONFLICT (match_id, participant_id) DO UPDATE SET
                        puuid                  = EXCLUDED.puuid,
                        champion               = EXCLUDED.champion,
                        position               = EXCLUDED.position,
                        kills                  = EXCLUDED.kills,
                        deaths                 = EXCLUDED.deaths,
                        assists                = EXCLUDED.assists,
                        win                    = EXCLUDED.win,
                        damage_to_champions    = EXCLUDED.damage_to_champions,
                        damage_taken           = EXCLUDED.damage_taken,
                        gold_earned            = EXCLUDED.gold_earned,
                        minions_killed         = EXCLUDED.minions_killed,
                        neutral_minions_killed = EXCLUDED.neutral_minions_killed,
                        vision_score           = EXCLUDED.vision_score,
                        wards_placed           = EXCLUDED.wards_placed,
                        item0 = EXCLUDED.item0,
                        item1 = EXCLUDED.item1,
                        item2 = EXCLUDED.item2,
                        item3 = EXCLUDED.item3,
                        item4 = EXCLUDED.item4,
                        item5 = EXCLUDED.item5,
                        item6 = EXCLUDED.item6,
                        summoner1_id = EXCLUDED.summoner1_id,
                        summoner2_id = EXCLUDED.summoner2_id,
                        team_id      = EXCLUDED.team_id,
                        champ_level        = EXCLUDED.champ_level,
                        primary_style_id   = EXCLUDED.primary_style_id,
                        secondary_style_id = EXCLUDED.secondary_style_id,
                        rune_ids           = EXCLUDED.rune_ids,
                        shard_ids          = EXCLUDED.shard_ids,
                        tier               = EXCLUDED.tier,
                        division           = EXCLUDED.division,
                        league_points      = EXCLUDED.league_points
                    """,
                    (
                        match_id,
                        puuid if followed else None,
                        participant["championName"],
                        participant["teamPosition"],
                        participant["kills"],
                        participant["deaths"],
                        participant["assists"],
                        participant["win"],
                        participant["totalDamageDealtToChampions"],
                        participant["totalDamageTaken"],
                        participant["goldEarned"],
                        participant["totalMinionsKilled"],
                        participant["neutralMinionsKilled"],
                        participant["visionScore"],
                        participant["wardsPlaced"],
                        participant["item0"],
                        participant["item1"],
                        participant["item2"],
                        participant["item3"],
                        participant["item4"],
                        participant["item5"],
                        participant["item6"],
                        participant["summoner1Id"],
                        participant["summoner2Id"],
                        participant["participantId"],
                        participant["teamId"],
                        participant["champLevel"],
                        primary_style_id,
                        secondary_style_id,
                        rune_ids,
                        shard_ids,
                        rank.get("tier"),
                        rank.get("rank"),
                        rank.get("leaguePoints"),
                    ),
                )

            if me is None:
                # Pasa en partidas raras, como los remakes. Sin el
                # invocador seguido la partida no sirve para nada.
                raise RuntimeError("El invocador no aparece entre los participantes")

            n_purchases, n_level_ups = save_timeline(cursor, match_id)

            # Se hace un commit por partida. Si una falla, las anteriores
            # ya están guardadas en vez de perderse todas en el rollback.
            connection.commit()

        # Cualquier error, a propósito. Una partida que falla no debe tumbar
        # la ejecución, y log.exception deja el rastro para ver si fue un bug.
        except Exception:
            connection.rollback()
            log.exception("Partida %s no guardada", match_id)
            continue

        saved += 1

        kda = f"{me['kills']}/{me['deaths']}/{me['assists']}"
        result = "Victoria" if me["win"] else "Derrota"
        log.info(
            "%-15s %-10s %-9s %s compras, %s habilidades",
            me["championName"],
            kda,
            result,
            n_purchases,
            n_level_ups,
        )

        time.sleep(0.1)

if refetch:
    log.info("Partidas actualizadas: %s", saved)
else:
    log.info("Partidas nuevas guardadas: %s", saved)
