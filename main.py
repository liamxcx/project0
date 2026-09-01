import os
import sys
from urllib.parse import quote

import requests
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("RIOT_API_KEY")
game_name = os.getenv("RIOT_GAME_NAME")
tag_line = os.getenv("RIOT_TAG_LINE")

print(f"Consultando datos de {game_name}#{tag_line}")

# ACCOUNT-V1 usa región grande (europe), no plataforma (euw1)
url = f"https://europe.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{quote(game_name)}/{tag_line}"

# La clave va en la cabecera, no en la URL: las URLs quedan en logs
response = requests.get(url, headers={"X-Riot-Token": api_key})

# 401/403 = clave inválida o caducada. 404 = Riot ID incorrecto.
if response.status_code != 200:
    print(f"Error al buscar la cuenta: {response.status_code}")
    sys.exit(1)

puuid = response.json()["puuid"]

url_partidas = f"https://europe.api.riotgames.com/lol/match/v5/matches/by-puuid/{puuid}/ids"

respuesta_partidas = requests.get(
    url_partidas,
    headers={"X-Riot-Token": api_key},
    params={"count": 5}
)

if respuesta_partidas.status_code != 200:
    print(f"Error al obtener las partidas: {respuesta_partidas.status_code}")
    sys.exit(1)

partidas = respuesta_partidas.json()

print(f"Encontradas {len(partidas)} partidas:")
for partida in partidas:
    print(f"  {partida}")