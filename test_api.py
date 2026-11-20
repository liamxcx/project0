import psycopg
import pytest
import redis
from fastapi.testclient import TestClient
from prometheus_client import REGISTRY

import api
from api import app, ladder_lp
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


def test_metrics_returns_prometheus_format():
    response = client.get("/metrics")

    assert response.status_code == 200
    # Texto plano en el formato de Prometheus, no JSON como el resto de rutas
    assert response.headers["content-type"].startswith("text/plain")
    # prometheus_client la registra de serie, así que sale aunque no haya métricas propias
    assert "python_info" in response.text


def requests_total(route, status):
    """Lee el contador de la API para una ruta y un código. Sin peticiones, 0."""
    labels = {"method": "GET", "route": route, "status": status}
    return REGISTRY.get_sample_value("http_requests_total", labels) or 0


def test_metrics_count_requests_by_route_template(full_match):
    # El contador vive en el proceso y suma también lo de otros tests, así que se
    # compara con el valor de antes y no con un número fijo
    before = requests_total("/matches/{match_id}", "200")

    client.get("/matches/EUW1_4")

    assert requests_total("/matches/{match_id}", "200") == before + 1


def test_metrics_group_unknown_urls_together():
    before = requests_total("unmatched", "404")

    client.get("/does-not-exist")
    client.get("/does-not-exist-either")

    assert requests_total("unmatched", "404") == before + 2


def test_summoners_returns_followed_summoners(seeded_db):
    response = client.get("/summoners")

    assert response.status_code == 200
    assert response.json() == [
        {
            "game_name": "Invocador",
            "tag_line": "TEST",
            "profile_icon_id": 29,
            "summoner_level": 100,
        }
    ]


def test_matches_returns_only_own_matches(seeded_db):
    response = client.get("/matches")

    assert response.status_code == 200
    matches = response.json()["matches"]

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
    assert [m["match_id"] for m in response.json()["matches"]] == ["EUW1_2", "EUW1_1"]

    # Un parche sin partidas devuelve una lista vacía, no un error
    response = client.get("/matches", params={"patch": "26.99"})
    assert response.json() == {"matches": [], "has_more": False}


def test_matches_filters_by_champion(seeded_db):
    response = client.get("/matches", params={"champion": "Ahri"})

    # Las dos partidas del invocador seguido con Ahri. La Ahri rival de EUW1_3 no cuenta.
    assert [m["match_id"] for m in response.json()["matches"]] == ["EUW1_2", "EUW1_1"]

    # Se combina con el parche, y Lux solo jugó en la 26.18
    response = client.get("/matches", params={"champion": "Lux", "patch": "26.17"})
    assert response.json() == {"matches": [], "has_more": False}


def test_matches_returns_pages_of_10(seeded_db):
    # Diez partidas con Jinx, más recientes que las de SEED_SQL
    with psycopg.connect(DB_URL) as connection:
        connection.execute(
            """
            INSERT INTO matches (match_id, played_at, duration_seconds, queue_id, game_version)
            SELECT 'EUW1_J' || n, '2026-10-01 20:00+02'::timestamptz + n * interval '1 hour',
                   1800, 420, '16.20.123.4567'
            FROM generate_series(1, 10) AS n;

            INSERT INTO participants
                (match_id, participant_id, puuid, champion, kills, deaths, assists, win)
            SELECT 'EUW1_J' || n, 1, 'yo', 'Jinx', 5, 5, 5, true
            FROM generate_series(1, 10) AS n;
            """
        )

    first_page = client.get("/matches").json()
    assert len(first_page["matches"]) == 10
    assert all(m["champion"] == "Jinx" for m in first_page["matches"])
    assert first_page["has_more"] is True

    # La segunda página son las tres de SEED_SQL, que son más antiguas
    second_page = client.get("/matches", params={"offset": 10}).json()
    second_ids = [m["match_id"] for m in second_page["matches"]]
    assert second_ids == ["EUW1_3", "EUW1_2", "EUW1_1"]
    assert second_page["has_more"] is False

    # Quedan justo 10. La página está llena, pero detrás no hay ninguna más
    last_ten = client.get("/matches", params={"offset": 3}).json()
    assert len(last_ten["matches"]) == 10
    assert last_ten["has_more"] is False

    # Un offset negativo no tiene sentido y FastAPI lo rechaza
    assert client.get("/matches", params={"offset": -1}).status_code == 422


def test_matches_includes_badge(full_match):
    response = client.get("/matches")

    # Las partidas de SEED_SQL solo tienen dos jugadores, así que no tienen nota
    badges = {m["match_id"]: m["badge"] for m in response.json()["matches"]}
    assert badges == {"EUW1_4": "MVP", "EUW1_3": None, "EUW1_2": None, "EUW1_1": None}


def test_match_detail_returns_me_and_players(full_match):
    response = client.get("/matches/EUW1_4")

    assert response.status_code == 200
    detail = response.json()
    assert detail["patch"] == "26.18"

    me = detail["me"]
    assert me["participant_id"] == 1
    # (10 + 1) de los 14 asesinatos de su equipo
    assert me["kill_participation_pct"] == 78.6
    # 30.000 de los 70.000 de daño de su equipo
    assert me["damage_share_pct"] == 42.9

    players = detail["players"]
    assert len(players) == 10
    # Cada uno con sus compras, en orden y en minutos. Las del 6 no se mezclan
    assert players[0]["purchases"] == [
        {"item_id": 1055, "minute": 0},
        {"item_id": 3089, "minute": 12},
    ]
    assert players[5]["purchases"] == [{"item_id": 1056, "minute": 0}]
    # Y sus habilidades en orden, sin la EVOLVE
    assert players[0]["skills"] == [1, 2, 3, 1]
    assert players[5]["skills"] == []
    # Solo los invocadores seguidos tienen nombre
    assert [p["riot_id"] for p in players if p["riot_id"]] == ["Invocador#TEST"]
    # Los cinco rivales empatan, y el sello va al de número más bajo
    badges = {p["participant_id"]: p["badge"] for p in players if p["badge"]}
    assert badges == {1: "MVP", 6: "BASTION"}
    # Cada jugador trae lo del marcador, no solo el invocador seguido. El 7 tiene 157
    # súbditos y 10 monstruos neutrales
    rival = players[6]
    assert rival["damage_to_champions"] == 10000
    assert rival["cs"] == 167
    assert rival["items"][0] == 3089
    assert rival["summoner_spells"] == [4, None]
    # Y el nivel, las runas y el rango, que se guardan desde la V11
    assert rival["champ_level"] == 17
    assert rival["primary_style_id"] == 8000
    assert rival["rune_ids"] == [8005, 9111, 9104, 8017, 8345, 8304]
    assert rival["shard_ids"] == [5005, 5008, 5011]
    assert rival["tier"] == "DIAMOND"
    assert rival["division"] == "III"
    assert rival["league_points"] == 45
    # Sin clasificatoria, el rango llega vacío y no como un error
    assert players[7]["tier"] is None


def test_match_detail_returns_404_for_unknown_match(seeded_db):
    response = client.get("/matches/EUW1_999")

    assert response.status_code == 404


def test_match_detail_is_cached_by_the_browser(full_match):
    response = client.get("/matches/EUW1_4")

    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["etag"].startswith('W/"')


def test_match_detail_returns_304_when_unchanged(full_match):
    etag = client.get("/matches/EUW1_4").headers["etag"]

    response = client.get("/matches/EUW1_4", headers={"If-None-Match": etag})

    assert response.status_code == 304
    assert response.content == b""


# Un 404 no se guarda, porque la partida puede aparecer más tarde
def test_missing_match_is_not_cached_by_the_browser(seeded_db):
    response = client.get("/matches/EUW1_999")

    assert "cache-control" not in response.headers


def test_match_detail_is_compressed(full_match):
    response = client.get("/matches/EUW1_4", headers={"Accept-Encoding": "gzip"})

    assert response.headers["content-encoding"] == "gzip"
    assert response.headers["vary"] == "Accept-Encoding"


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
    # Las tres partidas de SEED_SQL: dos victorias y una derrota
    assert response.json() == {
        "games": 3,
        "wins": 2,
        "losses": 1,
        "winrate_pct": 66.7,
    }


def test_summary_filters_by_patch(seeded_db):
    response = client.get("/summary", params={"patch": "26.17"})

    # EUW1_1 y EUW1_2: una victoria y una derrota
    assert response.json() == {
        "games": 2,
        "wins": 1,
        "losses": 1,
        "winrate_pct": 50.0,
    }


def test_rank_returns_the_latest_snapshot(seeded_db):
    # Dos snapshots de días seguidos. Vale el segundo, con 24 LP y una victoria más
    with psycopg.connect(DB_URL) as connection:
        connection.execute(
            """
            INSERT INTO ranked_snapshots
                (puuid, taken_at, tier, division, league_points, wins, losses,
                 next_cutoff_lp)
            VALUES
                ('yo', '2026-11-02 20:00+01', 'MASTER', 'I', 861, 617, 601, 1640),
                ('yo', '2026-11-03 20:00+01', 'MASTER', 'I', 885, 618, 601, 1651);
            """
        )

    rank = client.get("/rank").json()

    assert rank["league_points"] == 885
    assert rank["games"] == 1219
    # 618 de 1.219
    assert rank["winrate_pct"] == 50.7
    assert rank["next_cutoff_lp"] == 1651


def test_rank_is_null_without_snapshots(seeded_db):
    response = client.get("/rank")

    assert response.status_code == 200
    assert response.json() is None


def test_rank_history_keeps_the_last_snapshot_of_each_day(seeded_db):
    with psycopg.connect(DB_URL) as connection:
        connection.execute(
            """
            INSERT INTO ranked_snapshots
                (puuid, taken_at, tier, division, league_points, wins, losses)
            VALUES
                -- Dos snapshots del mismo día, hace dos días. Vale el de la noche
                ('yo', date_trunc('day', now()) - interval '2 days' + interval '10 hours',
                 'MASTER', 'I', 800, 610, 600),
                ('yo', date_trunc('day', now()) - interval '2 days' + interval '20 hours',
                 'MASTER', 'I', 850, 612, 600),
                ('yo', date_trunc('day', now()) - interval '1 day' + interval '12 hours',
                 'MASTER', 'I', 885, 618, 601),
                -- Fuera de los 30 días
                ('yo', now() - interval '40 days', 'DIAMOND', 'I', 50, 500, 500);
            """
        )

    history = client.get("/rank/history").json()

    assert [point["league_points"] for point in history] == [850, 885]
    # 7 rangos con divisiones por 400, más 885
    assert history[1]["ladder_lp"] == 3685


def test_ladder_lp_continues_across_divisions():
    assert ladder_lp("IRON", "IV", 0) == 0
    assert ladder_lp("GOLD", "IV", 0) == 1200
    # Al subir de Diamante I a Master la línea no salta
    assert ladder_lp("DIAMOND", "I", 100) == ladder_lp("MASTER", "I", 0) == 2800


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
    # (10 + 3 + 5 + 4) / (2 + 7)
    assert ahri["kda_ratio"] == 2.44


# Sin muertes no se puede dividir, así que el ratio llega vacío
def test_champions_kda_ratio_is_null_without_deaths(seeded_db):
    with psycopg.connect(DB_URL) as connection:
        connection.execute(
            """
            INSERT INTO matches (match_id, played_at, duration_seconds, queue_id, game_version)
            VALUES ('EUW1_T', '2026-09-05 20:00+02', 1800, 420, '16.18.123.4567');

            INSERT INTO participants
                (match_id, participant_id, puuid, champion, kills, deaths, assists, win)
            VALUES ('EUW1_T', 1, 'yo', 'Teemo', 4, 0, 6, true);
            """
        )

    response = client.get("/champions")

    teemo = next(c for c in response.json() if c["champion"] == "Teemo")
    assert teemo["kda_ratio"] is None


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

    # No se queda en las 20 últimas, así que Ahri y Lux siguen contando
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
    assert len(first.json()["matches"]) == 3

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
    assert len(response.json()["matches"]) == 3


def fake_kubernetes(monkeypatch, running):
    """Sustituye las llamadas a Kubernetes y devuelve los Jobs que se crean."""
    created = []
    monkeypatch.setattr(api.refresh, "get_cronjob", lambda: {"metadata": {}})
    monkeypatch.setattr(api.refresh, "collector_running", lambda cronjob: running)

    def create_job(cronjob):
        created.append(cronjob)
        return {"metadata": {"name": "collector-refresh-abc12"}}

    monkeypatch.setattr(api.refresh, "create_job", create_job)
    return created


@pytest.mark.with_cache
def test_refresh_launches_the_collector_and_then_waits(monkeypatch):
    created = fake_kubernetes(monkeypatch, running=False)

    first = client.post("/refresh")
    second = client.post("/refresh")

    assert first.status_code == 202
    assert first.json() == {"job": "collector-refresh-abc12"}
    # La segunda llega dentro de la espera, así que no lanza otro
    assert second.status_code == 429
    assert int(second.headers["Retry-After"]) > 0
    assert len(created) == 1


@pytest.mark.with_cache
def test_refresh_does_not_launch_while_the_collector_runs(monkeypatch):
    created = fake_kubernetes(monkeypatch, running=True)

    first = client.post("/refresh")
    second = client.post("/refresh")

    assert first.status_code == 409
    assert created == []
    # Sin nada lanzado no hay espera, así que la segunda vuelve a mirar y no da 429
    assert second.status_code == 409
