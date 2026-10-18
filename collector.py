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
    RIOT_BASE_URL,
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

    Es una petición extra por partida: el detalle y el timeline son dos
    endpoints distintos. Devuelve cuántas filas ha guardado de cada cosa.
    """
    response = fetch(f"{RIOT_BASE_URL}/lol/match/v5/matches/{match_id}/timeline")

    if response is None or response.status_code != 200:
        raise RuntimeError(f"Sin timeline para {match_id}")

    purchases = []
    level_ups = []

    for frame in response.json()["info"]["frames"]:
        for event in frame["events"]:
            # El participante 0 no existe, son artefactos del arranque
            participant_id = event.get("participantId", 0)
            if participant_id < 1:
                continue

            event_type = event["type"]

            if event_type == "ITEM_PURCHASED":
                purchases.append(
                    [match_id, participant_id, event["itemId"], event["timestamp"]]
                )

            elif event_type == "ITEM_UNDO" and event["afterId"] == 0:
                # Se busca la última compra de ese objeto y se quita, porque
                # esa compra no llegó a ocurrir. Con afterId distinto de 0
                # sería deshacer una venta, que no afecta aquí.
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

    # Con --refetch la partida puede tener filas de una pasada anterior. Como
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


log.info("Consultando datos de %s#%s", RIOT_GAME_NAME, RIOT_TAG_LINE)

account_response = fetch(
    f"{RIOT_BASE_URL}/riot/account/v1/accounts/by-riot-id/"
    f"{quote(RIOT_GAME_NAME)}/{RIOT_TAG_LINE}"
)

if account_response is None:
    log.error("No se ha podido conectar con la API tras varios intentos")
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
        log.error("La clave ha caducado. Regenérala en developer.riotgames.com")
    sys.exit(1)

puuid = account_response.json()["puuid"]

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

with (
    psycopg.connect(DB_URL) as connection,
    connection.cursor() as cursor,
):
    # El invocador va primero porque las participaciones lo referencian
    cursor.execute(
        """
        INSERT INTO summoners (puuid, game_name, tag_line)
        VALUES (%s, %s, %s)
        ON CONFLICT (puuid) DO NOTHING
        """,
        (puuid, RIOT_GAME_NAME, RIOT_TAG_LINE),
    )

    # Se comprueba sobre item_purchases, que es la última tabla que se
    # rellena. Una partida que esté ahí se guardó entera. Mirando matches se
    # daría por buena una partida cuyos participantes o timeline fallaran.
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
                # resto basta el número de jugador, su identidad no hace falta.
                followed = participant["puuid"] == puuid
                if followed:
                    me = participant

                cursor.execute(
                    """
                    INSERT INTO participants
                        (match_id, puuid, champion, position, kills, deaths, assists, win,
                         damage_to_champions, damage_taken, gold_earned,
                         minions_killed, neutral_minions_killed,
                         vision_score, wards_placed,
                         item0, item1, item2, item3, item4, item5, item6,
                         summoner1_id, summoner2_id, participant_id, team_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s,
                            %s, %s, %s,
                            %s, %s,
                            %s, %s,
                            %s, %s, %s, %s, %s, %s, %s,
                            %s, %s, %s, %s)
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
                        team_id      = EXCLUDED.team_id
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
                    ),
                )

            if me is None:
                # Pasa en partidas raras, como los remakes. Sin el
                # participante propio la partida no sirve para nada.
                raise RuntimeError("el invocador no aparece entre los participantes")

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
