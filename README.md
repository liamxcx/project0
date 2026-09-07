# Project 0

Herramienta personal de estadísticas de League of Legends.
Consume la API de Riot Games y guarda el historial de partidas en PostgreSQL.

Proyecto de aprendizaje: el objetivo es llegar a una aplicación
contenerizada con base de datos, API propia y frontend.

Solo se procesan partidas de Ranked Solo/Duo (queueId 420).

## Estado actual

Recolección, base de datos y API propia funcionando. Falta la caché, el
frontend y el despliegue.

### Cómo encajan las piezas

Recolección, de vez en cuando:

```
API de Riot  ──▶  collector  ──▶  PostgreSQL
```

Consulta, cada vez que alguien pregunta:

```
cliente  ──▶  api  ──▶  Redis        ¿está la respuesta cacheada?
                   └──▶  PostgreSQL   solo si no lo está
```

`collector` arranca, descarga, guarda y termina. `db`, `redis` y `api` se
quedan en marcha.

Ningún endpoint de la API llama a Riot: sirve solo lo que ya está guardado,
así que consultar las estadísticas no gasta peticiones. Y cuando la
respuesta está en Redis, tampoco se consulta PostgreSQL.

### Qué hay hecho

- **`collector`** — dado un Riot ID: PUUID (ACCOUNT-V1), identificadores
  de las últimas partidas (MATCH-V5), detalle de cada una y guardado de
  invocador, partida y participación sin duplicar. Antes de descargar
  consulta cuáles ya están en la base y se las salta, así que solo pide
  a Riot lo que le falta. Con reintentos ante fallos de red y control del
  límite de peticiones.
- **`db`** — tres tablas en PostgreSQL, volumen con nombre para
  que los datos sobrevivan a los reinicios y arranque ordenado con
  healthcheck.
- **`api`** — cuatro endpoints con FastAPI, agregados calculados en SQL y
  documentación interactiva automática en `/docs`.
- **`redis`** — caché de respuestas de la API, con caducidad automática y
  opcional: si Redis no responde, la API consulta PostgreSQL y sigue
  funcionando.

### Qué falta

- Refresco automático de las partidas
- Frontend para ver las estadísticas y comparar invocadores
- Copia de seguridad de la base de datos
- Despliegue en Kubernetes

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

MATCH_COUNT=20

REDIS_URL=redis://redis:6379/0
CACHE_TTL_SECONDS=60
```

El Riot ID va separado: si eres `TuNombre#EUW`, el nombre va en
`RIOT_GAME_NAME` y el tag en `RIOT_TAG_LINE`, sin almohadilla.

`MATCH_COUNT` es cuántas partidas recientes se le piden a Riot en cada
ejecución. Si falta, se usan 20. Como el `collector` no vuelve a pedir las
que ya tiene, subirlo solo cuesta peticiones la primera vez.

`CACHE_TTL_SECONDS` es cuántos segundos vive cada respuesta cacheada. Es
el desfase máximo entre lo que hay en PostgreSQL y lo que devuelve la API.
Subirlo alivia a PostgreSQL a costa de servir datos más viejos.

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
- `matches` — fecha, duración, tipo de cola y parche de cada partida
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
  posición, KDA, resultado, fecha, duración y parche, este último en las
  dos numeraciones: `game_version` tal como lo da Riot y `patch` como lo
  ve el jugador.
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
  "duration_seconds": 2268,
  "game_version": "16.17.810.4348",
  "patch": "26.17"
}
```

## Estructura

```
collector.py         baja partidas de Riot y las guarda    → servicio collector
api.py               sirve lo guardado, cuatro endpoints   → servicio api
config.py            la configuración, en un solo sitio    → lo importan los dos
schema.sql           summoners, matches, participants      → servicio db
Dockerfile           la imagen que comparten los dos servicios
docker-compose.yml   los cuatro servicios, el volumen y los healthchecks
requirements.txt     dependencias de Python, con versiones fijadas
.env                 los valores reales (fuera del repo y de la imagen)
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
y `api` lo sustituye por uvicorn.

El servicio `db` tiene un healthcheck con `pg_isready`, y `collector` usa
`depends_on` con `condition: service_healthy`. Sin eso, `depends_on`
solo esperaría a que el contenedor arrancase, no a que PostgreSQL
aceptase conexiones, y la aplicación podría fallar al conectar.

`config.py` centraliza la lectura del `.env`: `collector.py` y `api.py`
importan de ahí en vez de construir cada uno su cadena de conexión.

Redis es una pieza opcional a propósito. Las llamadas a la caché van
envueltas en `cache_get` y `cache_set`, que capturan cualquier error y lo
tratan como "no hay nada cacheado": la API responde igual, más lenta, y
deja un aviso en los logs. Una caché no debe tumbar el servicio. Por el
mismo motivo el cliente lleva `socket_timeout=1`: un Redis colgado sería
peor que un Redis caído.

`game_version` es la numeración interna de Riot, la que da la API. No
coincide con la que ve el jugador en el cliente: la pública va diez por
delante en el primer número (interna `16.17` = pública `26.17`), porque
cada serie interna corresponde a un año natural. El campo `patch` de
`/matches` hace esa conversión al vuelo; en la base solo se guarda el
valor original.

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

## Deuda técnica

- Migraciones para modificar el esquema sin perder datos. Ahora un cambio
  en `schema.sql` obliga a `docker compose down -v`, que borra el historial.
- Decidir si `/docs` y `/redoc` se desactivan al desplegar fuera de local.
  Se hace con `docs_url=None` al crear la aplicación.
