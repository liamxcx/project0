# Proyecto 0

Herramienta personal de estadísticas de League of Legends.
Consume la API de Riot Games para consultar el historial de partidas.

Proyecto de aprendizaje: el objetivo es llegar a una aplicación
contenerizada con base de datos, API propia y frontend.

## Estado actual

Script en Python que, dado un Riot ID:

1. Obtiene el PUUID de la cuenta (ACCOUNT-V1)
2. Lista los identificadores de las últimas partidas (MATCH-V5)
3. Descarga el detalle de cada partida y muestra campeón, KDA y resultado

Incluye reintentos ante fallos de red y control del límite de peticiones.

## Requisitos

- Docker, o bien Python 3.12 o superior
- Una clave de la API de Riot: https://developer.riotgames.com
  (la Development Key caduca cada 24 horas)

## Configuración

Copiar `.env.example` a `.env` y rellenar los tres valores:

```
RIOT_API_KEY=RGAPI-...
RIOT_GAME_NAME=TuNombre
RIOT_TAG_LINE=EUW
```

El Riot ID va separado: si eres `TuNombre#EUW`, el nombre va en
`RIOT_GAME_NAME` y el tag en `RIOT_TAG_LINE`, sin almohadilla.

## Ejecución con Docker

```bash
docker build -t project0 .
docker run --env-file .env project0
```

El `.env` no se copia dentro de la imagen: se lee al arrancar el
contenedor. Así la clave nunca queda grabada en la imagen y se puede
renovar sin reconstruir nada.

## Ejecución en local

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

Recordar activar el entorno antes de cada sesión:

```bash
source .venv/bin/activate
```

## Notas

Las rutas usan hosts distintos según la API. Las que usa este proyecto
(ACCOUNT-V1 y MATCH-V5) van por región grande: `europe.api.riotgames.com`.
Otras, como LEAGUE-V4 para el rango, usan la plataforma:
`euw1.api.riotgames.com`.

Códigos de error habituales:

- `401` / `403` — clave inválida o caducada, hay que regenerarla
- `404` — Riot ID incorrecto
- `429` — límite de peticiones superado (el script espera y reintenta)

Tras regenerar la clave puede tardar unos segundos en ser válida.

## Pendiente

- Persistir las partidas en PostgreSQL con Docker Compose
- API propia con FastAPI
- Frontend para visualizar las estadísticas
- Despliegue en Kubernetes