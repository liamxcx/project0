from fastapi import FastAPI

app = FastAPI(title="Estadísticas de LoL")


@app.get("/health")
def health():
    return {"estado": "ok"}
