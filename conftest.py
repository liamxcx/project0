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
DATOS = """
    INSERT INTO summoners (puuid, game_name, tag_line)
    VALUES ('yo', 'Invocador', 'TEST');

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

VACIAR = "TRUNCATE summoners, matches, participants, item_purchases, skill_levelups"


@pytest.fixture
def datos():
    """Deja la base con las tres partidas de DATOS y la vacía al acabar el test."""
    # Se importa aquí y no arriba porque config.py tiene que leerse después de
    # poner las variables de entorno.
    from config import DB_URL

    # Se vacía también antes por si una ejecución anterior se cortó a medias
    # y dejó filas.
    with psycopg.connect(DB_URL) as conexion:
        conexion.execute(VACIAR)
        conexion.execute(DATOS)

    yield

    with psycopg.connect(DB_URL) as conexion:
        conexion.execute(VACIAR)


def pytest_configure(config):
    # Sin registrarla, pytest avisa de que no conoce la marca
    config.addinivalue_line("markers", "con_cache: usa el Redis de test")


@pytest.fixture(autouse=True)
def sin_cache(request, monkeypatch):
    """Apaga Redis en cada test, salvo en los marcados con con_cache."""
    import api

    if request.node.get_closest_marker("con_cache"):
        # Se guarda aparte porque un test puede cambiar api.cache por otro
        redis_test = api.cache
        redis_test.flushdb()
        yield
        redis_test.flushdb()
    else:
        monkeypatch.setattr(api, "cache_get", lambda key: None)
        monkeypatch.setattr(api, "cache_set", lambda key, value: None)
        yield
