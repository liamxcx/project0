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
    RIOT_API_KEY,
    RIOT_BASE_URL,
    RIOT_GAME_NAME,
    RIOT_TAG_LINE,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("collector")

# Con --refetch se vuelven a pedir a Riot las partidas ya guardadas, para
# rellenar columnas añadidas después. Sin él, las que ya están se saltan.
refetch = "--refetch" in sys.argv


def fetch(url, params=None, attempts=3):
    for attempt in range(attempts):
        try:
            response = requests.get(
                url, headers={"X-Riot-Token": RIOT_API_KEY}, params=params
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

        return response

    return None


def guardar_timeline(cursor, match_id):
    """Descarga el timeline de una partida y guarda compras y habilidades.

    Es una petición extra por partida: el detalle y el timeline son dos
    endpoints distintos. Devuelve cuántas filas ha guardado de cada cosa.
    """
    response = fetch(f"{RIOT_BASE_URL}/lol/match/v5/matches/{match_id}/timeline")

    if response is None or response.status_code != 200:
        log.warning("Sin timeline para %s", match_id)
        return 0, 0

    compras = []
    habilidades = []

    for frame in response.json()["info"]["frames"]:
        for event in frame["events"]:
            # El participante 0 no existe: son artefactos del arranque
            participant_id = event.get("participantId", 0)
            if participant_id < 1:
                continue

            tipo = event["type"]

            if tipo == "ITEM_PURCHASED":
                compras.append(
                    [match_id, participant_id, event["itemId"], event["timestamp"]]
                )

            elif tipo == "ITEM_UNDO" and event["afterId"] == 0:
                # Deshacer una compra: se busca la última de ese objeto y se
                # quita, porque esa compra no llegó a ocurrir. Con afterId
                # distinto de 0 sería deshacer una venta, que no afecta aquí.
                for i in range(len(compras) - 1, -1, -1):
                    if (
                        compras[i][1] == participant_id
                        and compras[i][2] == event["beforeId"]
                    ):
                        del compras[i]
                        break

            elif tipo == "SKILL_LEVEL_UP":
                habilidades.append(
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
        compras,
    )
    cursor.executemany(
        """
        INSERT INTO skill_levelups
            (match_id, participant_id, skill_slot, level_up_type, timestamp_ms)
        VALUES (%s, %s, %s, %s, %s)
        """,
        habilidades,
    )

    return len(compras), len(habilidades)


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

ids_response = fetch(
    f"{RIOT_BASE_URL}/lol/match/v5/matches/by-puuid/{puuid}/ids",
    params={"count": MATCH_COUNT},
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
    # El invocador va primero: las participaciones lo referencian
    cursor.execute(
        """
        INSERT INTO summoners (puuid, game_name, tag_line)
        VALUES (%s, %s, %s)
        ON CONFLICT (puuid) DO NOTHING
        """,
        (puuid, RIOT_GAME_NAME, RIOT_TAG_LINE),
    )

    cursor.execute(
        "SELECT match_id FROM matches WHERE match_id = ANY(%s)",
        (match_ids,),
    )
    already_saved = {row[0] for row in cursor.fetchall()}

    if refetch:
        log.info("Modo --refetch: se vuelven a pedir las %s guardadas", len(already_saved))
        already_saved = set()
    elif already_saved:
        log.info("Ya guardadas, no se piden a Riot: %s", len(already_saved))

    for match_id in match_ids:
        if match_id in already_saved:
            continue

        match_response = fetch(f"{RIOT_BASE_URL}/lol/match/v5/matches/{match_id}")

        if match_response is None or match_response.status_code != 200:
            log.warning("No se ha podido descargar %s", match_id)
            continue

        info = match_response.json()["info"]

        me = None
        for participant in info["participants"]:
            if participant["puuid"] == puuid:
                me = participant
                break

        # Riot da la fecha en milisegundos desde 1970
        played_at = datetime.fromtimestamp(info["gameCreation"] / 1000, timezone.utc)

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

        cursor.execute(
            """
            INSERT INTO participants
                (match_id, puuid, champion, position, kills, deaths, assists, win,
                 damage_to_champions, damage_taken, gold_earned,
                 minions_killed, neutral_minions_killed,
                 vision_score, wards_placed,
                 item0, item1, item2, item3, item4, item5, item6,
                 summoner1_id, summoner2_id, participant_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s,
                    %s, %s,
                    %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s)
            ON CONFLICT (match_id, puuid) DO UPDATE SET
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
                participant_id = EXCLUDED.participant_id
            """,
            (
                match_id,
                puuid,
                me["championName"],
                me["teamPosition"],
                me["kills"],
                me["deaths"],
                me["assists"],
                me["win"],
                me["totalDamageDealtToChampions"],
                me["totalDamageTaken"],
                me["goldEarned"],
                me["totalMinionsKilled"],
                me["neutralMinionsKilled"],
                me["visionScore"],
                me["wardsPlaced"],
                me["item0"],
                me["item1"],
                me["item2"],
                me["item3"],
                me["item4"],
                me["item5"],
                me["item6"],
                me["summoner1Id"],
                me["summoner2Id"],
                me["participantId"],
            ),
        )

        n_compras, n_habilidades = guardar_timeline(cursor, match_id)

        saved += 1

        kda = f"{me['kills']}/{me['deaths']}/{me['assists']}"
        resultado = "Victoria" if me["win"] else "Derrota"
        log.info(
            "%-15s %-10s %-9s %s compras, %s habilidades",
            me["championName"],
            kda,
            resultado,
            n_compras,
            n_habilidades,
        )

        time.sleep(0.1)

    connection.commit()

if refetch:
    log.info("Partidas actualizadas: %s", saved)
else:
    log.info("Partidas nuevas guardadas: %s", saved)
