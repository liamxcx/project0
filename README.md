# Proyecto 0

Herramienta personal de estadísticas de League of Legends.
Consume la API de Riot Games para consultar el historial de partidas.

Proyecto de aprendizaje: el objetivo es llegar a una aplicación
contenerizada con base de datos, API propia y frontend.

## Estado actual

Script en Python que, dado un Riot ID:

1. Obtiene el PUUID de la cuenta (ACCOUNT-V1)
2. Lista los identificadores de las últimas partidas (MATCH-V5)
3. Descarga el detalle de la última partida y muestra campeón, KDA y resultado

## Requisitos

- Python 3.12 o superior
- Una clave de la API de Riot: https://developer.riotgames.com
  (la Development Key caduca cada 24 horas)

## Puesta en marcha

Crear el entorno virtual e instalar dependencias:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Copiar `.env.example` a `.env` y rellenar los tres valores:

```
RIOT_API_KEY=RGAPI-...
RIOT_GAME_NAME=TuNombre
RIOT_TAG_LINE=EUW
```

El Riot ID va separado: si eres `TuNombre#EUW`, el nombre va en
`RIOT_GAME_NAME` y el tag en `RIOT_TAG_LINE`, sin almohadilla.

## Uso

Activar el entorno antes de trabajar:

```bash
source .venv/bin/activate
python main.py
```

## Notas

Las rutas usan hosts distintos según la API:

- ACCOUNT-V1 y MATCH-V5 usan región grande: `europe.api.riotgames.com`
- LEAGUE-V4 usa plataforma: `euw1.api.riotgames.com`

Códigos de error habituales:

- `401` / `403` — clave inválida o caducada, hay que regenerarla
- `404` — Riot ID incorrecto
- `429` — se ha superado el límite de peticiones

## Pendiente

- Control del límite de peticiones (reintentos ante 429)
- Contenerizar con Docker
- Persistir las partidas en PostgreSQL
