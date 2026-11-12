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


def required_env(name):
    """Lee una variable del entorno y corta la ejecución si no está.

    Sin esto, una variable ausente se cuela como None dentro de la cadena de
    conexión y el fallo aparece mucho más tarde, al conectar, sin decir qué
    faltaba.
    """
    value = os.getenv(name)
    if not value:
        log.error("Falta la variable %s en el .env", name)
        sys.exit(1)
    return value


# Cuántas partidas recientes se piden a Riot en cada ejecución
MATCH_COUNT = int(os.getenv("MATCH_COUNT", "20"))

# Solo se procesan partidas de Ranked Solo/Duo.
RANKED_SOLO_QUEUE = 420

# LEAGUE-V4 nombra la misma cola con texto y no con número
RANKED_SOLO_QUEUE_TYPE = "RANKED_SOLO_5x5"

# ACCOUNT-V1 y MATCH-V5 usan región grande (europe), no plataforma (euw1)
RIOT_BASE_URL = "https://europe.api.riotgames.com"

# LEAGUE-V4, al revés, usa la plataforma
RIOT_PLATFORM_URL = "https://euw1.api.riotgames.com"

DB_HOST = os.getenv("DB_HOST", "db")

# Los tests usan una base aparte en el 5433 para no pisar la de verdad
DB_PORT = os.getenv("DB_PORT", "5432")

DB_URL = (
    f"postgresql://{required_env('POSTGRES_USER')}:{required_env('POSTGRES_PASSWORD')}"
    f"@{DB_HOST}:{DB_PORT}/{required_env('POSTGRES_DB')}"
)

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

# Segundos que vive cada respuesta cacheada
CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "60"))

# El tag de la imagen, que pone el chart. Va delante de cada clave de Redis para
# que dos versiones de la API no lean lo que guardó la otra en un despliegue
APP_VERSION = os.getenv("APP_VERSION", "dev")
