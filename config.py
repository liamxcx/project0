import os

from dotenv import load_dotenv

load_dotenv()

RIOT_API_KEY = os.getenv("RIOT_API_KEY")
RIOT_GAME_NAME = os.getenv("RIOT_GAME_NAME")
RIOT_TAG_LINE = os.getenv("RIOT_TAG_LINE")

# Cuántas partidas recientes se piden a Riot en cada ejecución
MATCH_COUNT = int(os.getenv("MATCH_COUNT", "20"))

# ACCOUNT-V1 y MATCH-V5 usan región grande (europe), no plataforma (euw1)
RIOT_BASE_URL = "https://europe.api.riotgames.com"

DB_URL = (
    f"postgresql://{os.getenv('POSTGRES_USER')}:{os.getenv('POSTGRES_PASSWORD')}"
    f"@{os.getenv('DB_HOST', 'db')}:5432/{os.getenv('POSTGRES_DB')}"
)

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

# Segundos que vive cada respuesta cacheada
CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "60"))
