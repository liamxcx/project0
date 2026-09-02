import os
import sys
import time
import psycopg
from urllib.parse import quote

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

for identificador in partidas:
    respuesta = pedir(f"{BASE}/lol/match/v5/matches/{identificador}")

    if respuesta is None or respuesta.status_code != 200:
        print(f"Error en {identificador}")
        continue

    participantes = respuesta.json()["info"]["participants"]

    yo = None
    for participante in participantes:
        if participante["puuid"] == puuid:
            yo = participante
            break

    kda = f"{yo['kills']}/{yo['deaths']}/{yo['assists']}"
    print(f"{yo['championName']:<15} {kda:<10} {'Victoria' if yo['win'] else 'Derrota'}")

    # Sin pausa, Riot corta la conexión antes de llegar al 429
    time.sleep(0.1)

with psycopg.connect(DB_URL) as conexion:
    with conexion.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM partidas")
        print(f"Partidas en la base de datos: {cursor.fetchone()[0]}")