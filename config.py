import logging
import os
import sys

from dotenv import load_dotenv

load_dotenv()

# El logging se configura aquí porque config.py es lo primero que importan
# collector.py y api.py. Si se configurara en ellos, los mensajes de este
# fichero saldrían antes de tiempo y sin formato.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

log = logging.getLogger("config")


def obligatoria(nombre):
    """Lee una variable del entorno y corta la ejecución si no está.

    Sin esto, una variable ausente se cuela como None dentro de la cadena de
    conexión y el fallo aparece mucho más tarde, al conectar, sin decir qué
    faltaba.
    """
    valor = os.getenv(nombre)
    if not valor:
        log.error("Falta la variable %s en el .env", nombre)
        sys.exit(1)
    return valor


RIOT_API_KEY = obligatoria("RIOT_API_KEY")
RIOT_GAME_NAME = obligatoria("RIOT_GAME_NAME")
RIOT_TAG_LINE = obligatoria("RIOT_TAG_LINE")

# Cuántas partidas recientes se piden a Riot en cada ejecución
MATCH_COUNT = int(os.getenv("MATCH_COUNT", "20"))

# ACCOUNT-V1 y MATCH-V5 usan región grande (europe), no plataforma (euw1)
RIOT_BASE_URL = "https://europe.api.riotgames.com"

DB_URL = (
    f"postgresql://{obligatoria('POSTGRES_USER')}:{obligatoria('POSTGRES_PASSWORD')}"
    f"@{os.getenv('DB_HOST', 'db')}:5432/{obligatoria('POSTGRES_DB')}"
)

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

# Segundos que vive cada respuesta cacheada
CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "60"))

# Orígenes que pueden leer las respuestas de la API desde un navegador.
# Varios se separan por comas. Se quitan los espacios de alrededor para que
# "http://a.com, http://b.com" funcione igual que sin el espacio.
CORS_ORIGINS = [
    origen.strip()
    for origen in os.getenv("CORS_ORIGINS", "http://localhost:8080").split(",")
    if origen.strip()
]
