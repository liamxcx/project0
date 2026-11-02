import psycopg
import pytest
import redis
from fastapi.testclient import TestClient

import api
from api import app
from config import DB_URL

# Llama a los endpoints sin levantar uvicorn ni abrir ningún puerto
client = TestClient(app)


def test_health_returns_ok():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"estado": "ok"}


def test_ready_returns_ok_when_postgres_is_up():
    response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"estado": "listo"}


def test_ready_returns_503_when_postgres_is_down(monkeypatch):
    # En el puerto 1 no escucha nadie, así que la conexión falla al momento
    monkeypatch.setattr(api, "DB_URL", "postgresql://test:test@localhost:1/test")

    response = client.get("/ready")

    assert response.status_code == 503


def test_summoners_returns_followed_summoners(seeded_db):
    response = client.get("/summoners")

    assert response.status_code == 200
    assert response.json() == [{"game_name": "Invocador", "tag_line": "TEST"}]


def test_matches_returns_only_own_matches(seeded_db):
    response = client.get("/matches")

    assert response.status_code == 200
    matches = response.json()

    # Tres partidas propias. Los Yasuo no tienen puuid y no deben aparecer.
    assert len(matches) == 3
    assert all(m["champion"] != "Yasuo" for m in matches)

    # La más reciente primero
    assert [m["match_id"] for m in matches] == ["EUW1_3", "EUW1_2", "EUW1_1"]

    # game_version 16.18 se enseña como parche 26.18
    assert matches[0]["patch"] == "26.18"


def test_matches_filters_by_patch(seeded_db):
    response = client.get("/matches", params={"patch": "26.17"})

    assert response.status_code == 200
    assert [m["match_id"] for m in response.json()] == ["EUW1_2", "EUW1_1"]

    # Un parche sin partidas devuelve una lista vacía, no un error
    response = client.get("/matches", params={"patch": "26.99"})
    assert response.json() == []


def test_matches_returns_pages_of_20(seeded_db):
    # Veinte partidas con Jinx, más recientes que las de SEED_SQL
    with psycopg.connect(DB_URL) as connection:
        connection.execute(
            """
            INSERT INTO matches (match_id, played_at, duration_seconds, queue_id, game_version)
            SELECT 'EUW1_J' || n, '2026-10-01 20:00+02'::timestamptz + n * interval '1 hour',
                   1800, 420, '16.20.123.4567'
            FROM generate_series(1, 20) AS n;

            INSERT INTO participants
                (match_id, participant_id, puuid, champion, kills, deaths, assists, win)
            SELECT 'EUW1_J' || n, 1, 'yo', 'Jinx', 5, 5, 5, true
            FROM generate_series(1, 20) AS n;
            """
        )

    first_page = client.get("/matches").json()
    assert len(first_page) == 20
    assert all(m["champion"] == "Jinx" for m in first_page)

    # La segunda página son las tres de SEED_SQL, que son más antiguas
    second_page = client.get("/matches", params={"offset": 20}).json()
    assert [m["match_id"] for m in second_page] == ["EUW1_3", "EUW1_2", "EUW1_1"]

    # Un offset negativo no tiene sentido y FastAPI lo rechaza
    assert client.get("/matches", params={"offset": -1}).status_code == 422


def test_matches_includes_badge(full_match):
    response = client.get("/matches")

    # Las partidas de SEED_SQL solo tienen dos jugadores, así que no tienen nota
    badges = {m["match_id"]: m["badge"] for m in response.json()}
    assert badges == {"EUW1_4": "MVP", "EUW1_3": None, "EUW1_2": None, "EUW1_1": None}


def test_match_detail_returns_me_and_players(full_match):
    response = client.get("/matches/EUW1_4")

    assert response.status_code == 200
    detail = response.json()
    assert detail["patch"] == "26.18"

    me = detail["me"]
    assert me["participant_id"] == 1
    # (10 + 1) de los 14 asesinatos de tu equipo
    assert me["kill_participation_pct"] == 78.6
    # 30.000 de los 70.000 de daño de tu equipo
    assert me["damage_share_pct"] == 42.9
    # Solo tus compras, en orden y en minutos
    assert me["purchases"] == [
        {"item_id": 1055, "minute": 0},
        {"item_id": 3089, "minute": 12},
    ]

    players = detail["players"]
    assert len(players) == 10
    # Solo los invocadores seguidos tienen nombre
    assert [p["riot_id"] for p in players if p["riot_id"]] == ["Invocador#TEST"]
    # Los cinco rivales empatan, y el sello va al de número más bajo
    badges = {p["participant_id"]: p["badge"] for p in players if p["badge"]}
    assert badges == {1: "MVP", 6: "BASTION"}


def test_match_detail_returns_404_for_unknown_match(seeded_db):
    response = client.get("/matches/EUW1_999")

    assert response.status_code == 404


def test_patches_counts_own_matches_newest_first(seeded_db):
    response = client.get("/patches")

    assert response.status_code == 200
    # EUW1_1 y EUW1_2 son de la 16.17 y EUW1_3 de la 16.18. Los rivales no cuentan.
    assert response.json() == [
        {"patch": "26.18", "games": 1},
        {"patch": "26.17", "games": 2},
    ]


def test_summary_of_the_season(seeded_db):
    response = client.get("/summary")

    assert response.status_code == 200
    # Las tres partidas de SEED_SQL: 14/13/29 en total y 5.400 segundos
    assert response.json() == {
        "games": 3,
        "wins": 2,
        "losses": 1,
        "winrate_pct": 66.7,
        "avg_kills": 4.7,
        "avg_deaths": 4.3,
        "avg_assists": 9.7,
        "kda_ratio": 3.31,
        "avg_duration_seconds": 1800,
    }


def test_summary_filters_by_patch(seeded_db):
    response = client.get("/summary", params={"patch": "26.17"})

    summary = response.json()
    # EUW1_1 y EUW1_2: una victoria y una derrota, (13 + 9) / 9 y 3.300 segundos
    assert summary["games"] == 2
    assert summary["winrate_pct"] == 50.0
    assert summary["kda_ratio"] == 2.44
    assert summary["avg_duration_seconds"] == 1650


def test_champions_groups_by_champion(seeded_db):
    response = client.get("/champions")

    assert response.status_code == 200
    champions = response.json()

    # Ahri (2 partidas) y Lux (1), en ese orden. Yasuo es de los rivales.
    assert [c["champion"] for c in champions] == ["Ahri", "Lux"]

    # Son 2 y no 3. La Ahri rival de EUW1_3 no cuenta.
    ahri = champions[0]
    assert ahri["games"] == 2
    assert ahri["wins"] == 1
    assert ahri["winrate_pct"] == 50.0
    # (10 + 3) / 2
    assert ahri["avg_kills"] == 6.5


def test_champions_counts_every_match_of_the_season(seeded_db):
    # Veinte partidas con Jinx, más recientes que las de SEED_SQL
    with psycopg.connect(DB_URL) as connection:
        connection.execute(
            """
            INSERT INTO matches (match_id, played_at, duration_seconds, queue_id, game_version)
            SELECT 'EUW1_J' || n, '2026-10-01 20:00+02'::timestamptz + n * interval '1 hour',
                   1800, 420, '16.20.123.4567'
            FROM generate_series(1, 20) AS n;

            INSERT INTO participants
                (match_id, participant_id, puuid, champion, kills, deaths, assists, win)
            SELECT 'EUW1_J' || n, 1, 'yo', 'Jinx', 5, 5, 5, true
            FROM generate_series(1, 20) AS n;
            """
        )

    response = client.get("/champions")

    # No se queda en las 20 últimas: Ahri y Lux siguen contando
    champions = response.json()
    assert [c["champion"] for c in champions] == ["Jinx", "Ahri", "Lux"]
    assert champions[0]["games"] == 20


def test_champions_ignores_previous_seasons(seeded_db):
    # Una partida con Zed de la temporada anterior, la 15
    with psycopg.connect(DB_URL) as connection:
        connection.execute(
            """
            INSERT INTO matches (match_id, played_at, duration_seconds, queue_id, game_version)
            VALUES ('EUW1_0', '2025-12-20 20:00+01', 1800, 420, '15.24.123.4567');

            INSERT INTO participants
                (match_id, participant_id, puuid, champion, kills, deaths, assists, win)
            VALUES ('EUW1_0', 1, 'yo', 'Zed', 5, 5, 5, true);
            """
        )

    response = client.get("/champions")

    assert [c["champion"] for c in response.json()] == ["Ahri", "Lux"]


def test_champions_filters_by_patch(seeded_db):
    response = client.get("/champions", params={"patch": "26.17"})

    # Lux solo jugó en la 26.18
    assert [c["champion"] for c in response.json()] == ["Ahri"]


@pytest.mark.with_cache
def test_second_call_does_not_hit_postgres(seeded_db):
    first = client.get("/matches")
    assert len(first.json()) == 3

    # Si la segunda llamada consultara la base, ya no encontraría ninguna
    with psycopg.connect(DB_URL) as connection:
        connection.execute("DELETE FROM matches")

    second = client.get("/matches")
    assert second.json() == first.json()


@pytest.mark.with_cache
def test_api_works_when_redis_is_down(seeded_db, monkeypatch):
    # En el puerto 1 no escucha nadie, así que cada llamada a Redis falla
    broken_redis = redis.Redis.from_url("redis://localhost:1/0", socket_timeout=1)
    monkeypatch.setattr(api, "cache", broken_redis)

    response = client.get("/matches")

    assert response.status_code == 200
    assert len(response.json()) == 3
