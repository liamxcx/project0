import os

import psycopg
import pytest

# pytest carga este fichero antes que los tests, así que estas variables ya
# están puestas cuando se importa la API y config.py lee la base y Redis.
os.environ["DB_HOST"] = "localhost"
os.environ["DB_PORT"] = "5433"
os.environ["POSTGRES_USER"] = "test"
os.environ["POSTGRES_PASSWORD"] = "test"
os.environ["POSTGRES_DB"] = "test"
os.environ["REDIS_URL"] = "redis://localhost:6380/0"

# Tres partidas inventadas. Ahri sale dos veces (una victoria y una derrota) y
# Lux una. En cada partida hay además un rival sin puuid, que la API no debe
# contar nunca. Hay dos con Yasuo, que tú no has jugado, y uno con Ahri, que
# sí, para comprobar que sus partidas no se suman a las tuyas.
SEED_SQL = """
    INSERT INTO summoners (puuid, game_name, tag_line, profile_icon_id, summoner_level)
    VALUES ('yo', 'Invocador', 'TEST', 29, 100);

    INSERT INTO matches (match_id, played_at, duration_seconds, queue_id, game_version)
    VALUES
        ('EUW1_1', '2026-09-01 20:00+02', 1800, 420, '16.17.123.4567'),
        ('EUW1_2', '2026-09-02 20:00+02', 1500, 420, '16.17.123.4567'),
        ('EUW1_3', '2026-09-03 20:00+02', 2100, 420, '16.18.123.4567');

    INSERT INTO participants
        (match_id, participant_id, puuid, champion, position, kills, deaths, assists, win)
    VALUES
        ('EUW1_1', 1, 'yo', 'Ahri',  'MIDDLE',  10,  2,  5, true),
        ('EUW1_1', 6, NULL, 'Yasuo', 'MIDDLE',   2, 10,  3, false),
        ('EUW1_2', 1, 'yo', 'Ahri',  'MIDDLE',   3,  7,  4, false),
        ('EUW1_2', 6, NULL, 'Yasuo', 'MIDDLE',   7,  3,  2, true),
        ('EUW1_3', 1, 'yo', 'Lux',   'UTILITY',  1,  4, 20, true),
        ('EUW1_3', 6, NULL, 'Ahri',  'MIDDLE',   5,  5,  5, false);
"""

# Una cuarta partida con los diez jugadores, para lo que necesita al equipo
# entero: la nota, los sellos y los porcentajes. Tú eres el jugador 1, el
# mejor en todo, y ganas. Las compras del jugador 6 no deben salir en las tuyas.
FULL_MATCH_SQL = """
    INSERT INTO matches (match_id, played_at, duration_seconds, queue_id, game_version)
    VALUES ('EUW1_4', '2026-09-04 20:00+02', 1800, 420, '16.18.123.4567');

    INSERT INTO participants
        (match_id, participant_id, puuid, champion, kills, deaths, assists,
         win, team_id, damage_to_champions, vision_score,
         minions_killed, neutral_minions_killed, item0, summoner1_id)
    SELECT 'EUW1_4', n, CASE WHEN n = 1 THEN 'yo' END, 'Ahri',
           CASE WHEN n = 1 THEN 10 ELSE 1 END, 5, 1,
           n <= 5, CASE WHEN n <= 5 THEN 100 ELSE 200 END,
           CASE WHEN n = 1 THEN 30000 ELSE 10000 END, 20,
           150 + n, 10, 3089, 4
    FROM generate_series(1, 10) AS n;

    INSERT INTO item_purchases (match_id, participant_id, item_id, timestamp_ms)
    VALUES
        ('EUW1_4', 1, 1055, 1500),
        ('EUW1_4', 1, 3089, 725000),
        ('EUW1_4', 6, 1056, 2000);
"""

CLEAR_SQL = (
    "TRUNCATE summoners, matches, participants, item_purchases, skill_levelups, "
    "ranked_snapshots"
)


@pytest.fixture
def seeded_db():
    """Deja la base con las tres partidas de SEED_SQL y la vacía al acabar el test."""
    # Se importa aquí y no arriba porque config.py tiene que leerse después de
    # poner las variables de entorno.
    from config import DB_URL

    # Se vacía también antes por si una ejecución anterior se cortó a medias
    # y dejó filas.
    with psycopg.connect(DB_URL) as connection:
        connection.execute(CLEAR_SQL)
        connection.execute(SEED_SQL)

    yield

    with psycopg.connect(DB_URL) as connection:
        connection.execute(CLEAR_SQL)


@pytest.fixture
def full_match(seeded_db):
    """Añade FULL_MATCH_SQL a los datos de seeded_db, que la borra al acabar."""
    from config import DB_URL

    with psycopg.connect(DB_URL) as connection:
        connection.execute(FULL_MATCH_SQL)


def pytest_configure(config):
    # Sin registrarla, pytest avisa de que no conoce la marca
    config.addinivalue_line("markers", "with_cache: usa el Redis de test")


@pytest.fixture(autouse=True)
def disable_cache(request, monkeypatch):
    """Apaga Redis en cada test, salvo en los marcados con with_cache."""
    import api

    if request.node.get_closest_marker("with_cache"):
        # Se guarda aparte porque un test puede cambiar api.cache por otro
        test_redis = api.cache
        test_redis.flushdb()
        yield
        test_redis.flushdb()
    else:
        monkeypatch.setattr(api, "cache_get", lambda key: None)
        monkeypatch.setattr(api, "cache_set", lambda key, value: None)
        yield
