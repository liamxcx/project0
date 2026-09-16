from fastapi.testclient import TestClient

from api import app

# Llama a los endpoints sin levantar uvicorn ni abrir ningún puerto
cliente = TestClient(app)


def test_health_responde_ok():
    respuesta = cliente.get("/health")

    assert respuesta.status_code == 200
    assert respuesta.json() == {"estado": "ok"}
