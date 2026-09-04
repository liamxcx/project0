import os
import sys
import time
from datetime import datetime, timezone
from urllib.parse import quote

import psycopg
import requests
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("RIOT_API_KEY")
game_name = os.getenv("RIOT_GAME_NAME")
tag_line = os.getenv("RIOT_TAG_LINE")

BASE = "https://europe.api.riotgames.com"

DB_URL = (
    f"postgresql://{os.getenv('POSTGRES_USER')}:{os.getenv('POSTGRES_PASSWORD')}"
    f"@{os.getenv('DB_HOST', 'db')}:5432/{os.getenv('POSTGRES_DB')}"
)


def pedir(url, params=None, intentos=3):
    for intento in range(intentos):
        try:
            respuesta = requests.get(url, headers={"X-Riot-Token": api_key}, params=params)
        except requests.exceptions.RequestException as error:
            espera = 2 ** intento
            print(f"Fallo de red ({error.__class__.__name__}), reintento en {espera}s")
            time.sleep(espera)
            continue

        if respuesta.status_code == 429:
            espera = int(respuesta.headers.get("Retry-After", 10))
            print(f"Límite alcanzado, esperando {espera}s")
            time.sleep(espera)
            continue

        return respuesta

    return None


print(f"Consultando datos de {game_name}#{tag_line}")

# ACCOUNT-V1 usa región grande (europe), no plataforma (euw1)
respuesta_cuenta = pedir(f"{BASE}/riot/account/v1/accounts/by-riot-id/{quote(game_name)}/{tag_line}")

if respuesta_cuenta is None:
    print("No se ha podido conectar con la API tras varios intentos")
    sys.exit(1)

if respuesta_cuenta.status_code != 200:
    codigos = {
        401: "no autorizado",
        403: "prohibido",
        404: "no encontrado",
        429: "demasiadas peticiones",
        500: "error interno del servidor",
        503: "servicio no disponible",
    }
    significado = codigos.get(respuesta_cuenta.status_code, "error desconocido")
    print(f"Error al obtener la cuenta: {respuesta_cuenta.status_code} ({significado})")

    if respuesta_cuenta.status_code in (401, 403):
        print("La clave ha caducado. Regenérala en developer.riotgames.com")
    sys.exit(1)

puuid = respuesta_cuenta.json()["puuid"]

respuesta_lista = pedir(f"{BASE}/lol/match/v5/matches/by-puuid/{puuid}/ids", params={"count": 2})

if respuesta_lista is None or respuesta_lista.status_code != 200:
    print("No se ha podido obtener la lista de partidas")
    sys.exit(1)

partidas = respuesta_lista.json()

print(f"Encontradas {len(partidas)} partidas\n")

nuevas = 0

with (
    psycopg.connect(DB_URL) as conexion,
    conexion.cursor() as cursor,
):

    # El invocador va primero: las participaciones lo referencian
    cursor.execute(
        """
        INSERT INTO summoners (puuid, game_name, tag_line)
        VALUES (%s, %s, %s)
        ON CONFLICT (puuid) DO NOTHING
        """,
        (puuid, game_name, tag_line),
    )

    for identificador in partidas:
        respuesta = pedir(f"{BASE}/lol/match/v5/matches/{identificador}")

        if respuesta is None or respuesta.status_code != 200:
            print(f"Error en {identificador}")
            continue

        info = respuesta.json()["info"]

        yo = None
        for participante in info["participants"]:
            if participante["puuid"] == puuid:
                yo = participante
                break

        # Riot da la fecha en milisegundos desde 1970
        fecha = datetime.fromtimestamp(info["gameCreation"] / 1000, timezone.utc)

        cursor.execute(
            """
            INSERT INTO matches (match_id, played_at, duration_seconds, queue_id)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (match_id) DO NOTHING
            """,
            (identificador, fecha, info["gameDuration"], info["queueId"]),
        )

        insertada = cursor.rowcount == 1

        cursor.execute(
            """
            INSERT INTO participants
                (match_id, puuid, champion, position, kills, deaths, assists, win)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (match_id, puuid) DO NOTHING
            """,
            (
                identificador,
                puuid,
                yo["championName"],
                yo["teamPosition"],
                yo["kills"],
                yo["deaths"],
                yo["assists"],
                yo["win"],
            ),
        )

        if insertada:
            nuevas += 1

        kda = f"{yo['kills']}/{yo['deaths']}/{yo['assists']}"
        marca = "nueva" if insertada else "ya estaba"
        print(f"{yo['championName']:<15} {kda:<10} {'Victoria' if yo['win'] else 'Derrota':<10} {marca}")

        time.sleep(0.1)

    conexion.commit()

print(f"\nGuardadas {nuevas} partidas nuevas")
