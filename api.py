import json
import logging

import psycopg
import redis
from fastapi import FastAPI, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from psycopg.rows import dict_row

from config import CACHE_TTL_SECONDS, CORS_ORIGINS, DB_URL, REDIS_URL

# El formato lo configura config.py, que se importa antes
log = logging.getLogger("api")

app = FastAPI(title="Estadísticas de LoL")

# Autoriza al frontend a leer las respuestas desde el navegador
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["GET"],
)

cache = redis.Redis.from_url(REDIS_URL, decode_responses=True, socket_timeout=1)


def cache_get(key):
    """Devuelve lo cacheado, o None si no está o si Redis falla."""
    try:
        return cache.get(key)
    except redis.RedisError:
        log.warning("Redis no disponible al leer %s", key)
        return None


def cache_set(key, value):
    """Guarda en caché. Si Redis falla, sigue adelante sin guardar."""
    try:
        cache.set(key, value, ex=CACHE_TTL_SECONDS)
    except redis.RedisError:
        log.warning("Redis no disponible al guardar %s", key)


CHAMPION_STATS_SELECT = """
    SELECT champion,
           COUNT(*) AS games,
           COUNT(*) FILTER (WHERE win) AS wins,
           ROUND(100.0 * COUNT(*) FILTER (WHERE win) / COUNT(*), 1) AS winrate_pct,
           ROUND(AVG(kills), 1) AS avg_kills,
           ROUND(AVG(deaths), 1) AS avg_deaths,
           ROUND(AVG(assists), 1) AS avg_assists
    FROM participants
    WHERE puuid IS NOT NULL
"""


@app.get("/health")
def health():
    return {"estado": "ok"}


@app.get("/matches")
def matches():
    key = "matches:latest"

    cached = cache_get(key)
    if cached is not None:
        return json.loads(cached)

    with (
        psycopg.connect(DB_URL, row_factory=dict_row) as connection,
        connection.cursor() as cursor,
    ):
        cursor.execute(
            """
            SELECT m.match_id,
                   p.champion,
                   p.position,
                   p.kills,
                   p.deaths,
                   p.assists,
                   p.win,
                   m.played_at,
                   m.duration_seconds,
                   m.game_version,
                   -- El parche público va 10 por delante del interno; ver el README
                   (split_part(m.game_version, '.', 1)::int + 10)
                       || '.' || split_part(m.game_version, '.', 2) AS patch
            FROM participants p
            JOIN matches m ON m.match_id = p.match_id
            -- participants guarda a los diez jugadores de cada partida, y
            -- solo los invocadores seguidos tienen puuid
            WHERE p.puuid IS NOT NULL
            ORDER BY m.played_at DESC
            LIMIT 20
            """
        )
        rows = jsonable_encoder(cursor.fetchall())

    cache_set(key, json.dumps(rows))
    return rows


@app.get("/champions")
def champions():
    key = "champions:all"

    cached = cache_get(key)
    if cached is not None:
        return json.loads(cached)

    with (
        psycopg.connect(DB_URL, row_factory=dict_row) as connection,
        connection.cursor() as cursor,
    ):
        cursor.execute(
            CHAMPION_STATS_SELECT
            + """
            GROUP BY champion
            ORDER BY games DESC, champion
            """
        )
        rows = jsonable_encoder(cursor.fetchall())

    cache_set(key, json.dumps(rows))
    return rows


@app.get("/champions/{champion}")
def champion_stats(champion: str):
    key = f"champions:{champion.lower()}"

    cached = cache_get(key)
    if cached is not None:
        row = json.loads(cached)
    else:
        with (
            psycopg.connect(DB_URL, row_factory=dict_row) as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute(
                CHAMPION_STATS_SELECT
                + """
                  AND LOWER(champion) = LOWER(%s)
                GROUP BY champion
                """,
                (champion,),
            )
            row = jsonable_encoder(cursor.fetchone())

        cache_set(key, json.dumps(row))

    if row is None:
        raise HTTPException(status_code=404, detail=f"Sin partidas con {champion}")

    return row
