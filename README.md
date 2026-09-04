# Project 0

Herramienta personal de estadísticas de League of Legends.
Consume la API de Riot Games y guarda el historial de partidas en PostgreSQL.

Proyecto de aprendizaje: el objetivo es llegar a una aplicación
contenerizada con base de datos, API propia y frontend.

Solo se procesan partidas de Ranked Solo/Duo (queueId 420).

## Estado actual

La aplicación, dado un Riot ID:

1. Obtiene el PUUID de la cuenta (ACCOUNT-V1)
2. Lista los identificadores de las últimas partidas de ranked (MATCH-V5)
3. Descarga el detalle de cada partida
4. Guarda invocador, partida y participación en PostgreSQL sin duplicar

Incluye reintentos ante fallos de red y control del límite de peticiones.
El arranque está ordenado: la aplicación espera a que PostgreSQL esté
listo para aceptar conexiones.

Hay además una API propia con FastAPI que sirve las partidas ya guardadas,
leyendo de PostgreSQL y sin volver a llamar a Riot.

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
DB_HOST=db
```

El Riot ID va separado: si eres `TuNombre#EUW`, el nombre va en
`RIOT_GAME_NAME` y el tag en `RIOT_TAG_LINE`, sin almohadilla.

`DB_HOST` es `db` dentro de Compose. Para ejecutar el script fuera de
Docker hay que ponerlo a `localhost`.

## Ejecución

```bash
docker compose up
```

Levanta los tres servicios. El esquema de `schema.sql` se aplica
automáticamente la primera vez que se inicializa la base de datos.

Los servicios no se comportan igual:

- `db` y `api` son procesos largos: se quedan corriendo hasta que se paran.
- `collector` es un script: descarga las partidas, las guarda y termina. En
  `docker compose ps` aparece como `Exited (0)`, que no es un error.

Para levantar solo la API, sin gastar peticiones a Riot:

```bash
docker compose up -d --build api
```

Qué comando usar según lo que hayas cambiado:

```bash
docker compose up            # cambios en docker-compose.yml o .env
docker compose up --build    # cambios en el código o en requirements.txt
docker compose down -v       # cambios en schema.sql (borra los datos)
```

El `--build` hace falta porque `collector.py`, `api.py`, `config.py` y
`requirements.txt` se copian dentro de la imagen. El resto se lee al
arrancar.

El `-v` hace falta con `schema.sql` porque el script solo se ejecuta
cuando la base de datos está vacía. Más adelante habría que sustituirlo
por migraciones para no perder el historial.

## Base de datos

Tres tablas:

- `summoners` — traduce cada PUUID a un Riot ID legible
- `matches` — fecha, duración y tipo de cola de cada partida
- `participants` — campeón, posición, KDA y resultado de un invocador
  en una partida

Las inserciones usan `ON CONFLICT DO NOTHING`, así que el script se puede
ejecutar las veces que haga falta: solo guarda lo que no tenía.

Los datos viven en el volumen `datos_db`, que sobrevive a `docker compose down`.

Para ver las partidas guardadas sin entrar en la base de datos:

```bash
docker compose exec db psql -U loltest -d lolstats -c "SELECT * FROM participants;"
```

## API

Servicio `api`, con FastAPI y uvicorn. Escucha en `http://localhost:8000`,
publicado solo en `127.0.0.1`.

Endpoints:

- `GET /health` — devuelve `{"estado": "ok"}`. No consulta la base de
  datos: solo confirma que el servicio responde.
- `GET /matches` — las 20 partidas más recientes, de la más nueva a la
  más antigua. Cruza `participants` con `matches` y devuelve campeón,
  posición, KDA, resultado, fecha y duración.
- `GET /champions` — un resumen por campeón: partidas jugadas, ganadas,
  winrate y KDA medio. Los agregados los calcula PostgreSQL con
  `GROUP BY`; ninguno de esos números está guardado en ninguna tabla.
- `GET /champions/{champion}` — lo mismo para un solo campeón. No
  distingue mayúsculas (`/champions/zeri` vale) y devuelve 404 si no hay
  partidas con ese campeón.

Al levantar `api`, Compose arranca antes `db` y espera a su healthcheck,
porque `/matches` no puede responder sin base de datos.

FastAPI genera la documentación sola a partir de las rutas registradas:

- `http://localhost:8000/docs` — documentación navegable
- `http://localhost:8000/openapi.json` — el esquema en crudo

Comprobación rápida:

```bash
curl http://localhost:8000/health
curl -s http://localhost:8000/matches | python3 -m json.tool
curl -s http://localhost:8000/champions | python3 -m json.tool
curl -s http://localhost:8000/champions/zeri | python3 -m json.tool
```

Un campeón de `/champions`:

```json
{
  "champion": "Zeri",
  "games": 2,
  "wins": 2,
  "winrate_pct": 100.0,
  "avg_kills": 9.5,
  "avg_deaths": 5.0,
  "avg_assists": 11.0
}
```

Una partida de `/matches`:

```json
{
  "champion": "Zeri",
  "position": "BOTTOM",
  "kills": 12,
  "deaths": 7,
  "assists": 15,
  "win": true,
  "played_at": "2026-08-28T12:21:15.912000+00:00",
  "duration_seconds": 2268
}
```

## Estructura

```
collector.py         descarga de partidas y guardado en la base de datos
api.py               API con FastAPI
config.py            configuración leída del .env, compartida por los dos
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

Dentro de la red de Compose los servicios se alcanzan por su nombre de
servicio, no por `localhost`.

`api` arranca uvicorn con `--host 0.0.0.0`. Por defecto uvicorn escucha en
`127.0.0.1`, que dentro del contenedor significa solo el propio contenedor:
el puerto quedaría publicado sin nadie escuchando detrás.

`collector` y `api` comparten Dockerfile y se diferencian por el `command`
del compose: `collector` usa el `CMD` de la imagen (`python collector.py`)
y `api` lo
sustituye por uvicorn.

El servicio `db` tiene un healthcheck con `pg_isready`, y `collector` usa
`depends_on` con `condition: service_healthy`. Sin eso, `depends_on`
solo esperaría a que el contenedor arrancase, no a que PostgreSQL
aceptase conexiones, y la aplicación podría fallar al conectar.

`config.py` centraliza la lectura del `.env`: `collector.py` y `api.py`
importan de ahí en vez de construir cada uno su cadena de conexión.

Los porcentajes viajan como números (`winrate_pct: 66.7`), sin el símbolo.
El formato es cosa de quien los muestre.

Los valores que llegan por la URL se pasan a la consulta como parámetros
(`%s` y una tupla), nunca interpolados en el texto SQL. Interpolarlos
abriría la puerta a la inyección SQL.

Las tablas, las columnas y las rutas están en inglés; los mensajes de la
consola, los comentarios y esta documentación, en español.

Códigos de error habituales de la API:

- `401` / `403` — clave inválida o caducada, hay que regenerarla
- `404` — Riot ID incorrecto
- `429` — límite de peticiones superado (el script espera y reintenta)

Tras regenerar la clave puede tardar unos segundos en ser válida.

## Pendiente

- Migraciones para modificar el esquema sin perder datos
- Caché con Redis y actualización programada
- Frontend para visualizar las estadísticas
- Despliegue en Kubernetes
