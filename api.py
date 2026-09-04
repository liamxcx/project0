import psycopg
from fastapi import FastAPI, HTTPException
from psycopg.rows import dict_row

from config import DB_URL

app = FastAPI(title="Estadísticas de LoL")

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
                   m.duration_seconds
            FROM participants p
            JOIN matches m ON m.match_id = p.match_id
            ORDER BY m.played_at DESC
            LIMIT 20
            """
        )
        return cursor.fetchall()


@app.get("/champions")
def champions():
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
        return cursor.fetchall()


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
