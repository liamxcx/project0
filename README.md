# Proyecto 0

Herramienta personal de estadísticas de League of Legends.
Consume la API de Riot Games y guarda el historial de partidas.

Proyecto de aprendizaje: el objetivo es llegar a una aplicación
contenerizada con base de datos, API propia y frontend.

Solo se procesan partidas de Ranked Solo/Duo (queueId 420).

## Estado actual

Script en Python que, dado un Riot ID:

1. Obtiene el PUUID de la cuenta (ACCOUNT-V1)
2. Lista los identificadores de las últimas partidas (MATCH-V5)
3. Descarga el detalle de cada partida y muestra campeón, KDA y resultado

Incluye reintentos ante fallos de red y control del límite de peticiones.

Hay una base de datos PostgreSQL levantada con su esquema, pendiente
de conectar con la aplicación.

## Requisitos

- Docker
- Una clave de la API de Riot: https://developer.riotgames.com
  (la Development Key caduca cada 24 horas)

## Configuración

Copiar `.env.example` a `.env` y rellenar los valores:

```
RIOT_API_KEY=RGAPI-...
RIOT_GAME_NAME=TuNombre
RIOT_TAG_LINE=EUW

POSTGRES_USER=lol
POSTGRES_PASSWORD=
POSTGRES_DB=lolstats
```

El Riot ID va separado: si eres `TuNombre#EUW`, el nombre va en
`RIOT_GAME_NAME` y el tag en `RIOT_TAG_LINE`, sin almohadilla.

## Ejecución con Docker Compose

```bash
docker compose up
```

Levanta dos servicios: la aplicación y una base de datos PostgreSQL.
El esquema de `schema.sql` se aplica automáticamente la primera vez
que se inicializa la base de datos.

Para parar y limpiar:

```bash
docker compose down
```

Para empezar de cero borrando también los datos:

```bash
docker compose down -v
```

Ese `-v` hace falta si se modifica `schema.sql`, porque el script solo
se ejecuta cuando la base de datos está vacía.

## Ejecución en local sin Docker

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

## Estructura

```
main.py              lógica de la aplicación
schema.sql           definición de las tablas
Dockerfile           imagen de la aplicación
docker-compose.yml   orquestación de los servicios
requirements.txt     dependencias de Python
```

## Notas

Las rutas usan hosts distintos según la API. Las que usa este proyecto
(ACCOUNT-V1 y MATCH-V5) van por región grande: `europe.api.riotgames.com`.
Otras, como LEAGUE-V4 para el rango, usan la plataforma:
`euw1.api.riotgames.com`.

Dentro de la red de Compose los servicios se alcanzan por su nombre,
no por `localhost`. El host de la base de datos es `db`.

Códigos de error habituales de la API:

- `401` / `403` — clave inválida o caducada, hay que regenerarla
- `404` — Riot ID incorrecto
- `429` — límite de peticiones superado (el script espera y reintenta)

Tras regenerar la clave puede tardar unos segundos en ser válida.

## Pendiente

- Conectar la aplicación con PostgreSQL y persistir las partidas
- API propia con FastAPI
- Caché con Redis y actualización programada
- Frontend para visualizar las estadísticas
- Despliegue en Kubernetes