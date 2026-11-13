import hashlib
import json
import logging

import psycopg
import redis
from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.gzip import GZipMiddleware
from psycopg.rows import dict_row

from config import APP_VERSION, CACHE_TTL_SECONDS, DB_URL, REDIS_URL

# El formato lo configura config.py, que se importa antes
log = logging.getLogger("api")

app = FastAPI(title="Estadísticas de LoL")
# Comprime las respuestas desde 500 bytes cuando el cliente lo pide. Va aquí y
# no en nginx ni en Traefik para que valga igual en Compose y en el clúster
app.add_middleware(GZipMiddleware)

# Con timeout, un Redis que no contesta no deja colgadas las peticiones
cache = redis.Redis.from_url(REDIS_URL, decode_responses=True, socket_timeout=1)


def cache_get(key):
    """Devuelve lo cacheado, o None si no está o si Redis falla."""
    try:
        return cache.get(f"{APP_VERSION}:{key}")
    except redis.RedisError as error:
        log.warning("No se ha podido leer %s de Redis: %s", key, error)
        return None


def cache_set(key, value):
    """Guarda en caché. Si Redis falla, sigue adelante sin guardar."""
    try:
        cache.set(f"{APP_VERSION}:{key}", value, ex=CACHE_TTL_SECONDS)
    except redis.RedisError as error:
        log.warning("No se ha podido guardar %s en Redis: %s", key, error)


CHAMPION_STATS_SELECT = """
    SELECT champion,
           COUNT(*) AS games,
           COUNT(*) FILTER (WHERE win) AS wins,
           ROUND(100.0 * COUNT(*) FILTER (WHERE win) / COUNT(*), 1) AS winrate_pct,
           ROUND(AVG(kills), 1) AS avg_kills,
           ROUND(AVG(deaths), 1) AS avg_deaths,
           ROUND(AVG(assists), 1) AS avg_assists,
           -- Con las sumas y no con las medias redondeadas, para que salga
           -- exacto. Sin ninguna muerte da null, porque no se puede dividir
           ROUND((SUM(kills) + SUM(assists))::numeric / NULLIF(SUM(deaths), 0), 2)
               AS kda_ratio
    FROM participants
    WHERE puuid IS NOT NULL
"""


# El parche público va 10 por delante del interno; ver el README. Se mete en
# las consultas con un f-string, y la tabla matches tiene que llevar el alias m.
PATCH_SQL = (
    "(split_part(m.game_version, '.', 1)::int + 10)"
    " || '.' || split_part(m.game_version, '.', 2)"
)

# Las partidas que cuentan para las estadísticas: las de un parche si se pide,
# y si no, las de la temporada actual. Va dentro de un WITH selected AS (...).
SELECTED_MATCHES_SQL = f"""
    SELECT m.match_id
    FROM participants p
    JOIN matches m ON m.match_id = p.match_id
    WHERE p.puuid IS NOT NULL
      AND CASE
          -- La temporada es el primer número de la versión interna, el mismo
          -- que el de la partida más reciente
          WHEN %(patch)s::text IS NULL THEN
              split_part(m.game_version, '.', 1) = (
                  SELECT split_part(game_version, '.', 1)
                  FROM matches
                  ORDER BY played_at DESC
                  LIMIT 1
              )
          ELSE {PATCH_SQL} = %(patch)s
      END
"""


# Solo dice que el proceso responde. No comprueba nada externo, porque
# Kubernetes reinicia el contenedor si falla y reiniciar no arregla la base.
@app.get("/health")
def health():
    return {"estado": "ok"}


# Comprueba Postgres porque sin él la API no puede responder nada útil.
# Mientras falle, Kubernetes deja de mandar tráfico a este pod.
@app.get("/ready")
def ready():
    try:
        with psycopg.connect(DB_URL, connect_timeout=2) as connection:
            connection.execute("SELECT 1")
    except psycopg.Error as error:
        # Con la causa se distingue un Postgres parado de una contraseña incorrecta o
        # de un problema de red, que también hacen fallar la readiness
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
            SELECT game_name, tag_line, profile_icon_id, summoner_level
            FROM summoners
            ORDER BY game_name
            """
        )
        rows = jsonable_encoder(cursor.fetchall())

    cache_set(key, json.dumps(rows))
    return rows


MATCHES_PAGE_SIZE = 10


@app.get("/matches")
def matches(
    patch: str | None = None,
    champion: str | None = None,
    offset: int = Query(default=0, ge=0),
):
    key = f"matches:{patch or 'all'}:{champion or 'all'}:{offset}"

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
              AND (%(champion)s::text IS NULL OR p.champion = %(champion)s)
            ORDER BY m.played_at DESC
            -- Se pide una de más para saber si hay otra página sin contarlas
            -- todas. La página pide la siguiente con offset=10, 20...
            LIMIT %(limit)s OFFSET %(offset)s
            """,
            {
                "patch": patch,
                "champion": champion,
                "offset": offset,
                "limit": MATCHES_PAGE_SIZE + 1,
            },
        )
        rows = jsonable_encoder(cursor.fetchall())

    page = {
        "matches": rows[:MATCHES_PAGE_SIZE],
        "has_more": len(rows) > MATCHES_PAGE_SIZE,
    }
    cache_set(key, json.dumps(page))
    return page


def load_match_detail(match_id):
    """Devuelve el detalle de una partida, o None si el invocador seguido no la jugó."""
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
            SELECT p.participant_id,
                   p.team_id,
                   p.champion,
                   p.position,
                   p.kills,
                   p.deaths,
                   p.assists,
                   p.win,
                   p.damage_to_champions,
                   p.minions_killed + p.neutral_minions_killed AS cs,
                   p.vision_score,
                   ARRAY[p.item0, p.item1, p.item2, p.item3, p.item4, p.item5, p.item6]
                       AS items,
                   ARRAY[p.summoner1_id, p.summoner2_id] AS summoner_spells,
                   p.champ_level,
                   p.primary_style_id,
                   p.secondary_style_id,
                   p.rune_ids,
                   p.shard_ids,
                   p.tier,
                   p.division,
                   p.league_points,
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

        cursor.execute(
            """
            SELECT participant_id, item_id, timestamp_ms / 60000 AS minute
            FROM item_purchases
            WHERE match_id = %s
            ORDER BY timestamp_ms, id
            """,
            (match_id,),
        )
        purchases = cursor.fetchall()

        # Solo las subidas normales. Las EVOLVE, de campeones como Kha'Zix, no
        # gastan punto de habilidad y no forman parte del orden
        cursor.execute(
            """
            SELECT participant_id, skill_slot
            FROM skill_levelups
            WHERE match_id = %s AND level_up_type = 'NORMAL'
            ORDER BY timestamp_ms, id
            """,
            (match_id,),
        )
        skills = cursor.fetchall()

    for player in players:
        number = player["participant_id"]
        player["purchases"] = [
            {"item_id": p["item_id"], "minute": p["minute"]}
            for p in purchases
            if p["participant_id"] == number
        ]
        player["skills"] = [
            s["skill_slot"] for s in skills if s["participant_id"] == number
        ]

    # Los datos de la partida van fuera de me, porque son de los diez
    match_fields = ["match_id", "played_at", "duration_seconds", "patch"]
    detail = {field: me.pop(field) for field in match_fields}
    detail["me"] = me
    detail["players"] = players
    return jsonable_encoder(detail)


def etag_of(body):
    """La huella de una respuesta. Cambia en cuanto cambia un solo carácter."""
    # Débil (W/), porque el gzip cambia los bytes que viajan pero no el contenido
    return f'W/"{hashlib.sha256(body.encode()).hexdigest()}"'


@app.get("/matches/{match_id}")
def match_detail(match_id: str, request: Request, response: Response):
    key = f"match:{match_id}"

    body = cache_get(key)
    if body is None:
        body = json.dumps(load_match_detail(match_id))
        cache_set(key, body)
    detail = json.loads(body)

    # El 404 crea su propia respuesta, sin las cabeceras de abajo. Así el navegador
    # no guarda una partida que el collector puede traer en su siguiente ejecución.
    if detail is None:
        raise HTTPException(status_code=404, detail=f"Sin la partida {match_id}")

    # El navegador guarda el detalle pero pregunta antes de usarlo. Así nunca usa
    # una copia vieja sin saberlo, aunque un despliegue cambie la respuesta
    etag = etag_of(body)
    headers = {"ETag": etag, "Cache-Control": "no-cache"}
    asked_for = [
        tag.strip() for tag in request.headers.get("if-none-match", "").split(",")
    ]
    if etag in asked_for:
        return Response(status_code=304, headers=headers)

    response.headers.update(headers)
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


@app.get("/summary")
def summary(patch: str | None = None):
    key = f"summary:{patch or 'season'}"

    cached = cache_get(key)
    if cached is not None:
        return json.loads(cached)

    with (
        psycopg.connect(DB_URL, row_factory=dict_row) as connection,
        connection.cursor() as cursor,
    ):
        cursor.execute(
            f"""
            WITH selected AS ({SELECTED_MATCHES_SQL})
            SELECT COUNT(*) AS games,
                   COUNT(*) FILTER (WHERE p.win) AS wins,
                   COUNT(*) FILTER (WHERE NOT p.win) AS losses,
                   ROUND(100.0 * COUNT(*) FILTER (WHERE p.win) / NULLIF(COUNT(*), 0), 1)
                       AS winrate_pct
            FROM participants p
            WHERE p.puuid IS NOT NULL
              AND p.match_id IN (SELECT match_id FROM selected)
            """,
            {"patch": patch},
        )
        row = jsonable_encoder(cursor.fetchone())

    cache_set(key, json.dumps(row))
    return row


# Hoy solo se sigue a un invocador, así que vale el snapshot más reciente de la
# tabla. Con varios habría que indicar de cuál se quiere el rango.
@app.get("/rank")
def rank():
    key = "rank:latest"

    cached = cache_get(key)
    if cached is not None:
        return json.loads(cached)

    with (
        psycopg.connect(DB_URL, row_factory=dict_row) as connection,
        connection.cursor() as cursor,
    ):
        cursor.execute(
            """
            SELECT tier,
                   division,
                   league_points,
                   wins + losses AS games,
                   wins,
                   losses,
                   ROUND(100.0 * wins / NULLIF(wins + losses, 0), 1) AS winrate_pct,
                   next_cutoff_lp,
                   taken_at
            FROM ranked_snapshots
            ORDER BY taken_at DESC
            LIMIT 1
            """
        )
        # Sin ningún snapshot, porque no hay clasificatoria, la API devuelve null
        row = jsonable_encoder(cursor.fetchone())

    cache_set(key, json.dumps(row))
    return row


# Rangos con divisiones, de menor a mayor. Cada uno son 400 LP, cuatro de 100
DIVISION_TIERS = ["IRON", "BRONZE", "SILVER", "GOLD", "PLATINUM", "EMERALD", "DIAMOND"]
DIVISIONS = ["IV", "III", "II", "I"]


# LP contados desde Hierro IV con 0, para que la gráfica no baje a 0 al subir de
# división. Master, Grandmaster y Challenger siguen la cuenta donde acaba Diamante
def ladder_lp(tier, division, league_points):
    if tier in DIVISION_TIERS:
        return (
            DIVISION_TIERS.index(tier) * 400
            + DIVISIONS.index(division) * 100
            + league_points
        )
    return len(DIVISION_TIERS) * 400 + league_points


# Como en /rank, hoy solo se sigue a un invocador, así que valen todos los snapshots
@app.get("/rank/history")
def rank_history():
    key = "rank:history"

    cached = cache_get(key)
    if cached is not None:
        return json.loads(cached)

    with (
        psycopg.connect(DB_URL, row_factory=dict_row) as connection,
        connection.cursor() as cursor,
    ):
        # El último snapshot de cada día de los últimos 30. Los días se cuentan en
        # UTC, la zona de la base, para no meter la zona horaria en la API
        cursor.execute(
            """
            SELECT DISTINCT ON (taken_at::date)
                   taken_at::date AS day,
                   tier,
                   division,
                   league_points
            FROM ranked_snapshots
            WHERE taken_at >= now() - interval '30 days'
            ORDER BY taken_at::date, taken_at DESC
            """
        )
        rows = jsonable_encoder(cursor.fetchall())

    for row in rows:
        row["ladder_lp"] = ladder_lp(row["tier"], row["division"], row["league_points"])

    cache_set(key, json.dumps(rows))
    return rows


@app.get("/champions")
def champions(patch: str | None = None):
    key = f"champions:{patch or 'season'}"

    cached = cache_get(key)
    if cached is not None:
        return json.loads(cached)

    with (
        psycopg.connect(DB_URL, row_factory=dict_row) as connection,
        connection.cursor() as cursor,
    ):
        cursor.execute(
            f"""
            WITH selected AS ({SELECTED_MATCHES_SQL})
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
