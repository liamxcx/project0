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


def test_champion_stats_is_case_insensitive(seeded_db):
    response = client.get("/champions/ahri")

    assert response.status_code == 200
    assert response.json()["champion"] == "Ahri"


def test_champion_stats_ignores_opponents(seeded_db):
    # Yasuo está en la base, pero solo en filas de rivales
    response = client.get("/champions/Yasuo")

    assert response.status_code == 404


def test_champion_stats_returns_404_when_not_played(seeded_db):
    response = client.get("/champions/Garen")

    assert response.status_code == 404


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
