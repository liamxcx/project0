import os
from urllib.parse import quote

import requests
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("RIOT_API_KEY")
game_name = os.getenv("RIOT_GAME_NAME")
tag_line = os.getenv("RIOT_TAG_LINE")

print(f"Consultando datos de {game_name}#{tag_line}")

url = f"https://europe.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{quote(game_name)}/{tag_line}"

response = requests.get(url, headers={"X-Riot-Token": api_key})

print(response.status_code)
print(response.json())