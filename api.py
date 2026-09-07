import json

import psycopg
import redis
from fastapi import FastAPI, HTTPException
from fastapi.encoders import jsonable_encoder
from psycopg.rows import dict_row

from config import CACHE_TTL_SECONDS, DB_URL, REDIS_URL

app = FastAPI(title="Estadísticas de LoL")

cache = redis.Redis.from_url(REDIS_URL, decode_responses=True)

CHAMPION_STATS_SELECT = """
    SELECT champion,
           COUNT(*) AS games,
           COUNT(*) FILTER (WHERE win) AS wins,
           ROUND(100.0 * COUNT(*) FILTER (WHERE win) / COUNT(*), 1) AS winrate_pct,
           ROUND(AVG(kills), 1) AS avg_kills,
           ROUND(AVG(deaths), 1) AS avg_deaths,
           ROUND(AVG(assists), 1) AS avg_assists
    FROM participants
"""


@app.get("/health")
def health():
    return {"estado": "ok"}


@app.get("/matches")
def matches():
    with (
        psycopg.connect(DB_URL, row_factory=dict_row) as connection,
        connection.cursor() as cursor,
    ):
        cursor.execute(
            """
            SELECT p.champion,
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
            ORDER BY m.played_at DESC
            LIMIT 20
            """
        )
        return cursor.fetchall()


@app.get("/champions")
def champions():
    key = "champions:all"

    cached = cache.get(key)
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

    cache.setex(key, CACHE_TTL_SECONDS, json.dumps(rows))
    return rows


@app.get("/champions/{champion}")
def champion_stats(champion: str):
    with (
        psycopg.connect(DB_URL, row_factory=dict_row) as connection,
        connection.cursor() as cursor,
    ):
        cursor.execute(
            CHAMPION_STATS_SELECT
            + """
            WHERE LOWER(champion) = LOWER(%s)
            GROUP BY champion
            """,
            (champion,),
        )
        row = cursor.fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail=f"Sin partidas con {champion}")

    return row
