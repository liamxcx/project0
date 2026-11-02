import json
import logging

import psycopg
import redis
from fastapi import FastAPI, HTTPException
from fastapi.encoders import jsonable_encoder
from psycopg.rows import dict_row

from config import CACHE_TTL_SECONDS, DB_URL, REDIS_URL

# El formato lo configura config.py, que se importa antes
log = logging.getLogger("api")

app = FastAPI(title="Estadísticas de LoL")

cache = redis.Redis.from_url(REDIS_URL, decode_responses=True, socket_timeout=1)


def cache_get(key):
    """Devuelve lo cacheado, o None si no está o si Redis falla."""
    try:
        return cache.get(key)
    except redis.RedisError as error:
        log.warning("No se ha podido leer %s de Redis: %s", key, error)
        return None


def cache_set(key, value):
    """Guarda en caché. Si Redis falla, sigue adelante sin guardar."""
    try:
        cache.set(key, value, ex=CACHE_TTL_SECONDS)
    except redis.RedisError as error:
        log.warning("No se ha podido guardar %s en Redis: %s", key, error)


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


# El parche público va 10 por delante del interno; ver el README. Se mete en
# las consultas con un f-string, y la tabla matches tiene que llevar el alias m.
PATCH_SQL = (
    "(split_part(m.game_version, '.', 1)::int + 10)"
    " || '.' || split_part(m.game_version, '.', 2)"
)


# Solo dice que el proceso responde. No comprueba nada externo, porque
# Kubernetes reinicia el contenedor si falla y reiniciar no arregla la base.
@app.get("/health")
def health():
    return {"estado": "ok"}


# Comprueba PostgreSQL porque sin él la API no puede responder nada útil.
# Mientras falle, Kubernetes deja de mandar tráfico a este pod.
@app.get("/ready")
def ready():
    try:
        with psycopg.connect(DB_URL, connect_timeout=2) as connection:
            connection.execute("SELECT 1")
    except psycopg.Error as error:
        # Con la causa se distingue un Postgres parado de una contraseña mal o de
        # un problema de red, que también hacen fallar la readiness
        log.warning("No se ha podido consultar PostgreSQL desde /ready: %s", error)
        raise HTTPException(status_code=503, detail="PostgreSQL no disponible")

    return {"estado": "listo"}


# Solo los invocadores seguidos tienen fila en summoners, porque de los otros
# nueve jugadores de cada partida no se guarda la identidad
@app.get("/summoners")
def summoners():
    key = "summoners:all"

    cached = cache_get(key)
    if cached is not None:
        return json.loads(cached)

    with (
        psycopg.connect(DB_URL, row_factory=dict_row) as connection,
        connection.cursor() as cursor,
    ):
        cursor.execute(
            """
            SELECT game_name, tag_line
            FROM summoners
            ORDER BY game_name
            """
        )
        rows = jsonable_encoder(cursor.fetchall())

    cache_set(key, json.dumps(rows))
    return rows


@app.get("/matches")
def matches(patch: str | None = None):
    key = f"matches:{patch or 'latest'}"

    cached = cache_get(key)
    if cached is not None:
        return json.loads(cached)

    with (
        psycopg.connect(DB_URL, row_factory=dict_row) as connection,
        connection.cursor() as cursor,
    ):
        cursor.execute(
            f"""
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
                   {PATCH_SQL} AS patch,
                   s.badge
            FROM participants p
            JOIN matches m ON m.match_id = p.match_id
            JOIN participant_scores s
                ON s.match_id = p.match_id AND s.participant_id = p.participant_id
            -- participants guarda a los diez jugadores de cada partida, y
            -- solo los invocadores seguidos tienen puuid
            WHERE p.puuid IS NOT NULL
              AND (%(patch)s::text IS NULL OR {PATCH_SQL} = %(patch)s)
            ORDER BY m.played_at DESC
            LIMIT %(limit)s
            """,
            # Sin parche, las 20 últimas. Con parche, todas las de ese parche,
            # porque LIMIT NULL en PostgreSQL es sin límite.
            {"patch": patch, "limit": None if patch else 20},
        )
        rows = jsonable_encoder(cursor.fetchall())

    cache_set(key, json.dumps(rows))
    return rows


def load_match_detail(match_id):
    """Devuelve el detalle de una partida, o None si no hay ninguna tuya con ese id."""
    with (
        psycopg.connect(DB_URL, row_factory=dict_row) as connection,
        connection.cursor() as cursor,
    ):
        # Hoy solo se sigue a un invocador. Con varios en la misma partida
        # habría que indicar de cuál se quiere el detalle.
        cursor.execute(
            f"""
            SELECT m.match_id,
                   m.played_at,
                   m.duration_seconds,
                   {PATCH_SQL} AS patch,
                   p.participant_id,
                   p.champion,
                   p.position,
                   p.kills,
                   p.deaths,
                   p.assists,
                   p.win,
                   p.damage_to_champions,
                   p.damage_taken,
                   p.gold_earned,
                   p.minions_killed + p.neutral_minions_killed AS cs,
                   p.vision_score,
                   p.wards_placed,
                   ROUND(100.0 * (p.kills + p.assists) / NULLIF(t.kills, 0), 1)
                       AS kill_participation_pct,
                   ROUND(100.0 * p.damage_to_champions / NULLIF(t.damage, 0), 1)
                       AS damage_share_pct,
                   ARRAY[p.item0, p.item1, p.item2, p.item3, p.item4, p.item5, p.item6]
                       AS items,
                   ARRAY[p.summoner1_id, p.summoner2_id] AS summoner_spells
            FROM participants p
            JOIN matches m ON m.match_id = p.match_id
            -- Totales de cada equipo. Las partidas guardadas antes de tener a
            -- los diez no tienen team_id, y ahí los porcentajes salen a NULL.
            LEFT JOIN (
                SELECT team_id,
                       SUM(kills) AS kills,
                       SUM(damage_to_champions) AS damage
                FROM participants
                WHERE match_id = %(match_id)s
                GROUP BY team_id
            ) t ON t.team_id = p.team_id
            WHERE p.match_id = %(match_id)s
              AND p.puuid IS NOT NULL
            """,
            {"match_id": match_id},
        )
        me = cursor.fetchone()
        if me is None:
            return None

        cursor.execute(
            """
            SELECT item_id, timestamp_ms / 60000 AS minute
            FROM item_purchases
            WHERE match_id = %s AND participant_id = %s
            ORDER BY timestamp_ms, id
            """,
            (match_id, me["participant_id"]),
        )
        me["purchases"] = cursor.fetchall()

        cursor.execute(
            """
            SELECT p.participant_id,
                   p.team_id,
                   p.champion,
                   p.position,
                   p.kills,
                   p.deaths,
                   p.assists,
                   p.win,
                   su.game_name || '#' || su.tag_line AS riot_id,
                   sc.score,
                   sc.badge
            FROM participants p
            JOIN participant_scores sc
                ON sc.match_id = p.match_id AND sc.participant_id = p.participant_id
            LEFT JOIN summoners su ON su.puuid = p.puuid
            WHERE p.match_id = %s
            ORDER BY p.participant_id
            """,
            (match_id,),
        )
        players = cursor.fetchall()

    # Los datos de la partida van fuera de me, porque son de los diez
    match_fields = ["match_id", "played_at", "duration_seconds", "patch"]
    detail = {field: me.pop(field) for field in match_fields}
    detail["me"] = me
    detail["players"] = players
    return jsonable_encoder(detail)


@app.get("/matches/{match_id}")
def match_detail(match_id: str):
    key = f"match:{match_id}"

    cached = cache_get(key)
    if cached is not None:
        detail = json.loads(cached)
    else:
        detail = load_match_detail(match_id)
        cache_set(key, json.dumps(detail))

    if detail is None:
        raise HTTPException(status_code=404, detail=f"Sin la partida {match_id}")

    return detail


@app.get("/patches")
def patches():
    key = "patches:all"

    cached = cache_get(key)
    if cached is not None:
        return json.loads(cached)

    with (
        psycopg.connect(DB_URL, row_factory=dict_row) as connection,
        connection.cursor() as cursor,
    ):
        cursor.execute(
            f"""
            SELECT {PATCH_SQL} AS patch,
                   COUNT(*) AS games
            FROM participants p
            JOIN matches m ON m.match_id = p.match_id
            WHERE p.puuid IS NOT NULL
            GROUP BY patch
            ORDER BY MAX(m.played_at) DESC
            """
        )
        rows = jsonable_encoder(cursor.fetchall())

    cache_set(key, json.dumps(rows))
    return rows


@app.get("/champions")
def champions(patch: str | None = None):
    # Lleva "list" para no chocar con las claves de /champions/{champion}
    key = f"champions:list:{patch or 'season'}"

    cached = cache_get(key)
    if cached is not None:
        return json.loads(cached)

    with (
        psycopg.connect(DB_URL, row_factory=dict_row) as connection,
        connection.cursor() as cursor,
    ):
        cursor.execute(
            f"""
            WITH selected AS (
                SELECT m.match_id
                FROM participants p
                JOIN matches m ON m.match_id = p.match_id
                WHERE p.puuid IS NOT NULL
                  AND CASE
                      -- Sin parche, la temporada actual. Es el primer número de la
                      -- versión interna, el mismo que el de la partida más reciente.
                      WHEN %(patch)s::text IS NULL THEN
                          split_part(m.game_version, '.', 1) = (
                              SELECT split_part(game_version, '.', 1)
                              FROM matches
                              ORDER BY played_at DESC
                              LIMIT 1
                          )
                      ELSE {PATCH_SQL} = %(patch)s
                  END
            )
            {CHAMPION_STATS_SELECT}
              AND match_id IN (SELECT match_id FROM selected)
            GROUP BY champion
            ORDER BY games DESC, champion
            """,
            {"patch": patch},
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
