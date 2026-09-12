# Project 0

Herramienta personal de estadísticas de League of Legends.
Consume la API de Riot Games y guarda el historial de partidas en PostgreSQL.

Proyecto de aprendizaje: el objetivo es llegar a una aplicación
contenerizada con base de datos, API propia y frontend.

Solo se procesan partidas de Ranked Solo/Duo (queueId 420).

## Estado actual

Recolección, base de datos, API propia y una página que la consume,
todo funcionando. Falta el despliegue.

### Cómo encajan las piezas

Recolección, cada hora sin que nadie la lance:

```
scheduler  ──cada hora──▶  collector  ──▶  API de Riot
                               │
                               └──▶  PostgreSQL
```

Consulta, cada vez que alguien pregunta:

```
navegador  ──▶  frontend   :8080   la página (nginx, ficheros estáticos)
     │
     └────────▶  api       :8000  ──▶  Redis        ¿está cacheada?
                                  └──▶  PostgreSQL   solo si no lo está
```

El navegador hace dos viajes: uno al `frontend` a por la página y otro a
la `api` a por los datos. Son dos puertos distintos, o sea dos orígenes
distintos, y por eso la API tiene que autorizar al frontend (ver CORS).

`collector` arranca, descarga, guarda y termina; lo lanza `scheduler`, que
es lo único que hace: ejecutarlo y volver a dormirse. `db`, `redis`, `api` y
`scheduler` se quedan en marcha.

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
- **`scheduler`** — ejecuta el `collector` cada cierto tiempo, así que las
  partidas nuevas aparecen solas.
- **`frontend`** — nginx sirviendo una página estática que pide los datos
  a la API desde el navegador.

### Qué falta

- Tabla de partidas, gráfica de winrate y comparar invocadores
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
REFRESH_INTERVAL_SECONDS=3600
TZ=Europe/Madrid
CORS_ORIGINS=http://localhost:8080
```

El Riot ID va separado: si eres `TuNombre#EUW`, el nombre va en
`RIOT_GAME_NAME` y el tag en `RIOT_TAG_LINE`, sin almohadilla.

`MATCH_COUNT` es cuántas partidas recientes se le piden a Riot en cada
ejecución. Si falta, se usan 20. Como el `collector` no vuelve a pedir las
que ya tiene, subirlo solo cuesta peticiones la primera vez.

`TZ` es la zona horaria de los contenedores, y es la que sale en los logs.
La convención en servidores es `UTC`; aquí está en hora local porque el
proyecto se lee desde Madrid.

`REFRESH_INTERVAL_SECONDS` es cada cuánto el `scheduler` vuelve a ejecutar
el `collector`. Una hora es razonable: las partidas no aparecen más rápido
que eso, y como el `collector` no vuelve a pedir las que ya tiene, un
intervalo corto tampoco gastaría peticiones de más.

`CACHE_TTL_SECONDS` es cuántos segundos vive cada respuesta cacheada. Es
el desfase máximo entre lo que hay en PostgreSQL y lo que devuelve la API.
Subirlo alivia a PostgreSQL a costa de servir datos más viejos.

`CORS_ORIGINS` son los orígenes que pueden leer las respuestas de la API
desde un navegador. Varios se separan por comas, y van sin barra final.
Cambia según dónde se despliegue, por eso es configuración y no código.

`DB_HOST` es `db` dentro de Compose. Para ejecutar el script fuera de
Docker hay que ponerlo a `localhost`.

## Ejecución

```bash
docker compose up
```

Levanta los siete servicios. El esquema lo aplica `flyway` antes de que
arranquen `collector`, `scheduler` y `api`.

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
docker compose up            # cambios en el esquema (una migración nueva)
```

El `--build` hace falta porque `collector.py`, `api.py`, `config.py` y
`requirements.txt` se copian dentro de la imagen. El resto se lee al
arrancar.

Y va sin nombrar servicio a propósito. `collector`, `scheduler` y `api`
comparten el `Dockerfile`, pero Compose construye una imagen por servicio:
`docker compose up --build api` reconstruye solo esa y deja a las otras dos
con el código anterior, sin dar ningún error. Para levantar uno suelto sí
vale nombrarlo; para reconstruir, no.

Los cambios de esquema ya no necesitan `down -v`: se escriben como una
migración nueva y `flyway` la aplica al arrancar, sin tocar los datos.
Ver [Migraciones](#migraciones).

## Base de datos

Tres tablas:

- `summoners` — traduce cada PUUID a un Riot ID legible
- `matches` — fecha, duración, tipo de cola y parche de cada partida
- `participants` — todo lo de un invocador en una partida: campeón,
  posición, KDA, resultado, oro, daño hecho y recibido, CS, visión,
  objetos finales y hechizos de invocador

Todos esos datos vienen en la misma respuesta de MATCH-V5, así que
guardarlos no cuesta ninguna petición extra a Riot.

El CS va en dos columnas, `minions_killed` y `neutral_minions_killed`,
porque Riot lo da así. Sumarlas es cosa de la consulta:

```sql
SELECT champion, minions_killed + neutral_minions_killed AS cs
FROM participants;
```

Los objetos y los hechizos se guardan como identificadores numéricos; los
nombres y los iconos salen de Data Dragon, igual que con los campeones.

### Insertar sin duplicar

Las inserciones usan `ON CONFLICT ... DO UPDATE`: si la fila no está se
inserta, y si está se actualiza con los valores nuevos. El script se puede
ejecutar las veces que haga falta y el resultado es siempre el mismo.

`DO NOTHING` no valdría: ignoraría la fila entera y nunca se podrían
rellenar columnas añadidas más tarde.

### Rellenar datos hacia atrás

El `collector` se salta las partidas que ya tiene, para no gastar
peticiones. Con `--refetch` las vuelve a pedir y reescribe las filas:

```bash
docker compose run --rm collector python collector.py --refetch
```

Hace falta al añadir una columna nueva (las partidas viejas la tendrían a
`NULL`) y al corregir un fallo del `collector` que haya guardado algo mal.

Solo alcanza a las partidas que Riot todavía sirve, unas cien hacia atrás.
Las más antiguas no se pueden volver a pedir, así que una columna añadida
tarde se queda con `NULL` para siempre en esas.

### El ciclo completo para añadir un dato

1. Escribir la migración con la columna nueva (`V4__...sql`)
2. Añadirla al `INSERT` del `collector`, en la lista de columnas, en los
   `%s` y en la tupla de valores
3. `docker compose up -d --build`, que aplica la migración y reconstruye
4. `--refetch` para rellenar el historial
5. Exponerla en `api.py` si el frontend la necesita

Los datos viven en el volumen `datos_db`, que sobrevive a `docker compose down`.

Para ver las partidas guardadas sin entrar en la base de datos:

```bash
docker compose exec db psql -U loltest -d lolstats -P pager=off \
  -c "SELECT champion, kills, gold_earned, damage_to_champions FROM participants;"
```

`-P pager=off` evita que la salida se abra en un paginador y deje el
terminal esperando.

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

Al levantar `api`, Compose arranca antes `db` y `redis` y espera a sus
healthchecks.

Los tres endpoints de datos se cachean en Redis con estas claves:

```
GET /matches              →  matches:latest
GET /champions            →  champions:all
GET /champions/{champion} →  champions:<campeón en minúsculas>
```

`/health` no se cachea: devuelve una constante. Y las respuestas vacías
también se guardan (`champions:garen` vale `null`), para que preguntar por
un campeón que no existe no consulte PostgreSQL cada vez.

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

## Migraciones

El esquema de la base vive en `migrations/`, un fichero por cambio:

```
migrations/
  V1__initial_schema.sql            summoners, matches, participants
  V2__index_matches_played_at.sql   índice para el ORDER BY de /matches
```

El nombre es la convención de Flyway: `V`, el número, **dos** guiones
bajos y la descripción. Con un solo guion el fichero se ignora.

Cada fichero lleva solo su cambio, no el esquema entero. El estado de la
base es la suma de todos, como los commits de un repositorio.

### Cómo se aplican

El servicio `flyway` se ejecuta al arrancar, aplica lo que falte y
termina. `collector`, `scheduler` y `api` esperan a que acabe bien
(`service_completed_successfully`), así que si una migración falla la
aplicación no arranca, en vez de trabajar sobre una base a medias.

Flyway lleva la cuenta en una tabla de la propia base,
`flyway_schema_history`, que se puede consultar como cualquier otra.

### Añadir un cambio

Crear el fichero con el número siguiente y levantar:

```bash
docker compose up -d
docker compose logs flyway
```

Comandos sueltos, sin levantar nada:

```bash
docker compose run --rm flyway info      # en qué versión está la base
docker compose run --rm flyway migrate   # aplicar lo que falte
docker compose run --rm flyway validate  # comprobar que nada ha cambiado
```

### Una migración aplicada no se toca

Flyway guarda el checksum de cada fichero ejecutado y lo recalcula en cada
arranque. Cambiar una migración ya aplicada, aunque sea un comentario, da
error y no se ejecuta nada.

No es una manía: si se editara una migración que lleva meses en
producción, un entorno nuevo aplicaría la versión corregida y producción
se quedaría con la vieja, sin que nadie se entere. ¿Hay que corregir algo?
Se escribe la migración siguiente.

### La base actual se incorporó con baseline

Cuando se montó Flyway, las tablas ya existían con partidas dentro. En vez
de vaciar la base se usó `flyway baseline -baselineVersion=1`, que crea la
tabla de control y apunta la V1 como aplicada sin ejecutarla.

Hace falta solo al meter Flyway en una base que ya existe. Una base vacía
ejecuta las migraciones desde la V1 y llega al mismo esquema.

## Frontend

Una página en `frontend/index.html` que pide los datos a la API y los
pinta. Se abre en `http://localhost:8080`.

La sirve nginx, no la API: son dos servicios y dos puertos. Servir los
estáticos con un servidor web dedicado es lo estándar, y deja el camino
abierto a ponerle delante un reverse proxy más adelante.

La carpeta entra en el contenedor como un bind mount de solo lectura, así
que editar el HTML y recargar el navegador basta: no hay que reconstruir
ni reiniciar nada. Si el cambio no se ve, suele ser la caché del
navegador (`Cmd + Shift + R`).

### CORS

La página vive en `http://localhost:8080` y la API en
`http://localhost:8000`. Distinto puerto es distinto origen, y por defecto
el navegador no deja que una página lea respuestas de otro origen.

La API lo autoriza con `CORSMiddleware`, que añade la cabecera
`Access-Control-Allow-Origin` a sus respuestas. Se comprueba en la pestaña
Network del navegador, en las cabeceras de respuesta de `/champions`.

Solo se autoriza el método `GET`, que es lo único que hace la API. Y esto
no protege la API: `curl` y cualquier cosa que no sea un navegador siguen
accediendo igual. CORS protege al usuario, no al servidor.

## Logs

Todo se registra con `logging`, con hora, nivel y mensaje:

```
2026-09-09 03:38:41  INFO     Partidas encontradas: 6
2026-09-09 03:42:50  WARNING  Redis no disponible al leer champions:all
```

Los niveles: `INFO` para el curso normal, `WARNING` para lo que va mal pero
no impide seguir (un reintento, Redis caído), y `ERROR` para lo que corta la
ejecución (clave caducada, API inalcanzable).

```bash
docker compose logs -f scheduler              # seguir en directo
docker compose logs --tail 20 api             # las últimas 20 líneas
docker compose logs --since 3h scheduler      # las últimas 3 horas
docker compose logs scheduler | grep WARNING  # solo los problemas
```

El `Dockerfile` define `PYTHONUNBUFFERED=1`. Sin eso Python acumula la
salida en un buffer y la suelta al terminar, así que los mensajes de un
servicio que no termina nunca, como `api`, llegarían tarde.

Los logs se rotan para que no crezcan sin límite: cada servicio guarda
como mucho 3 ficheros de 10 MB, y al abrir el cuarto se borra el más
viejo. Son 30 MB por servicio como techo. Sin esto el `scheduler`, que
escribe cada hora y no termina nunca, acabaría llenando el disco.

La configuración está en el bloque `x-logging` del `docker-compose.yml`,
y cada servicio la referencia con `logging: *default-logging`. Los
cambios ahí solo afectan a contenedores nuevos:

```bash
docker compose up -d --force-recreate
docker inspect project0-scheduler-1 --format '{{json .HostConfig.LogConfig}}'
```

## Estructura

```
collector.py         baja partidas de Riot y las guarda    → servicio collector
api.py               sirve lo guardado, cuatro endpoints   → servicio api
frontend/index.html  la página que consume la API          → servicio frontend
config.py            la configuración, en un solo sitio    → lo importan los dos
migrations/          el esquema, versionado paso a paso      → servicio flyway
Dockerfile           la imagen que comparten los dos servicios
docker-compose.yml   los seis servicios, el volumen y los healthchecks
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

`api.py` y `collector.py` llaman los dos a `logging.basicConfig`. uvicorn
configura solo sus propios loggers, así que sin esa llamada los mensajes de
la API saldrían sin formato y los de nivel `INFO` no se verían.

`scheduler` usa la misma imagen que `collector` y lo único que cambia es el
comando: un bucle de shell que ejecuta `collector.py` y duerme. El script no
sabe que se le está repitiendo, lo que deja el camino abierto a sustituir el
bucle por un CronJob cuando toque desplegar en Kubernetes.

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

- Decidir si `/docs` y `/redoc` se desactivan al desplegar fuera de local.
  Se hace con `docs_url=None` al crear la aplicación.
