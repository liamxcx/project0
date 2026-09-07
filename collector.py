import sys
import time
from datetime import datetime, timezone
from urllib.parse import quote

import psycopg
import requests

from config import DB_URL, RIOT_API_KEY, RIOT_BASE_URL, RIOT_GAME_NAME, RIOT_TAG_LINE


def fetch(url, params=None, attempts=3):
    for attempt in range(attempts):
        try:
            response = requests.get(
                url, headers={"X-Riot-Token": RIOT_API_KEY}, params=params
            )
        except requests.exceptions.RequestException as error:
            delay = 2**attempt
            print(f"Fallo de red ({error.__class__.__name__}), reintento en {delay}s")
            time.sleep(delay)
            continue

        if response.status_code == 429:
            delay = int(response.headers.get("Retry-After", 10))
            print(f"Límite alcanzado, esperando {delay}s")
            time.sleep(delay)
            continue

        return response

    return None


print(f"Consultando datos de {RIOT_GAME_NAME}#{RIOT_TAG_LINE}")

account_response = fetch(
    f"{RIOT_BASE_URL}/riot/account/v1/accounts/by-riot-id/"
    f"{quote(RIOT_GAME_NAME)}/{RIOT_TAG_LINE}"
)

if account_response is None:
    print("No se ha podido conectar con la API tras varios intentos")
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
    print(f"Error al obtener la cuenta: {account_response.status_code} ({meaning})")

    if account_response.status_code in (401, 403):
        print("La clave ha caducado. Regenérala en developer.riotgames.com")
    sys.exit(1)

puuid = account_response.json()["puuid"]

ids_response = fetch(
    f"{RIOT_BASE_URL}/lol/match/v5/matches/by-puuid/{puuid}/ids", params={"count": 2}
)

if ids_response is None or ids_response.status_code != 200:
    print("No se ha podido obtener la lista de partidas")
    sys.exit(1)

match_ids = ids_response.json()

print(f"Encontradas {len(match_ids)} partidas\n")

new_matches = 0

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

    if already_saved:
        print(f"{len(already_saved)} ya guardadas, no se piden a Riot")

    for match_id in match_ids:
        if match_id in already_saved:
            continue

        match_response = fetch(f"{RIOT_BASE_URL}/lol/match/v5/matches/{match_id}")

        if match_response is None or match_response.status_code != 200:
            print(f"Error en {match_id}")
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
            INSERT INTO matches (match_id, played_at, duration_seconds, queue_id)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (match_id) DO NOTHING
            """,
            (match_id, played_at, info["gameDuration"], info["queueId"]),
        )

        cursor.execute(
            """
            INSERT INTO participants
                (match_id, puuid, champion, position, kills, deaths, assists, win)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (match_id, puuid) DO NOTHING
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
            ),
        )

        new_matches += 1

        kda = f"{me['kills']}/{me['deaths']}/{me['assists']}"
        resultado = "Victoria" if me["win"] else "Derrota"
        print(f"{me['championName']:<15} {kda:<10} {resultado}")

        time.sleep(0.1)

    connection.commit()

print(f"\nGuardadas {new_matches} partidas nuevas")
