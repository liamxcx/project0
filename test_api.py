from fastapi.testclient import TestClient

from api import app

# Llama a los endpoints sin levantar uvicorn ni abrir ningún puerto
cliente = TestClient(app)


def test_health_responde_ok():
    respuesta = cliente.get("/health")

    assert respuesta.status_code == 200
    assert respuesta.json() == {"estado": "ok"}


def test_matches_devuelve_solo_las_propias(datos):
    respuesta = cliente.get("/matches")

    assert respuesta.status_code == 200
    partidas = respuesta.json()

    # Tres partidas propias. Los Yasuo no tienen puuid y no deben aparecer.
    assert len(partidas) == 3
    assert all(p["champion"] != "Yasuo" for p in partidas)

    # La más reciente primero
    assert [p["match_id"] for p in partidas] == ["EUW1_3", "EUW1_2", "EUW1_1"]

    # game_version 16.18 se enseña como parche 26.18
    assert partidas[0]["patch"] == "26.18"


def test_champions_agrupa_por_campeon(datos):
    respuesta = cliente.get("/champions")

    assert respuesta.status_code == 200
    campeones = respuesta.json()

    # Ahri (2 partidas) y Lux (1), en ese orden. Yasuo es de los rivales.
    assert [c["champion"] for c in campeones] == ["Ahri", "Lux"]

    # Son 2 y no 3. La Ahri rival de EUW1_3 no cuenta.
    ahri = campeones[0]
    assert ahri["games"] == 2
    assert ahri["wins"] == 1
    assert ahri["winrate_pct"] == 50.0
    # (10 + 3) / 2
    assert ahri["avg_kills"] == 6.5


def test_champion_stats_no_distingue_mayusculas(datos):
    respuesta = cliente.get("/champions/ahri")

    assert respuesta.status_code == 200
    assert respuesta.json()["champion"] == "Ahri"


def test_champion_stats_ignora_a_los_rivales(datos):
    # Yasuo está en la base, pero solo en filas de rivales
    respuesta = cliente.get("/champions/Yasuo")

    assert respuesta.status_code == 404


def test_champion_stats_devuelve_404_si_no_lo_has_jugado(datos):
    respuesta = cliente.get("/champions/Garen")

    assert respuesta.status_code == 404
