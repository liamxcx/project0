# Project 0

Herramienta personal de estadísticas de League of Legends.
Consume la API de Riot Games y guarda el historial de partidas en PostgreSQL.

Proyecto de aprendizaje: el objetivo es llegar a una aplicación
contenerizada con base de datos, API propia y frontend.

Solo se procesan partidas de Ranked Solo/Duo (queueId 420).

## Estado actual

Recolección, base de datos con migraciones, API propia y una página que la
consume, todo funcionando. Faltan los tests y el despliegue.

### Cómo encajan las piezas

Al arrancar, `flyway` pone el esquema al día y solo entonces arrancan los
servicios que usan la base:

```
db ──sano──▶ flyway ──termina──▶ collector / scheduler / api
```

Recolección, cada hora sin que nadie la lance:

```
scheduler  ──cada hora──▶  collector  ──▶  API de Riot
                               │              detalle de la partida
                               │              y su timeline
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

`collector` arranca, descarga, guarda y termina. Lo lanza `scheduler`, que
solo hace eso: ejecutarlo y esperar hasta la siguiente vez. `db`, `redis`,
`api`, `frontend` y `scheduler` se quedan en marcha.

Ningún endpoint de la API llama a Riot: sirve solo lo que ya está guardado,
así que consultar las estadísticas no gasta peticiones. Y cuando la
respuesta está en Redis, tampoco se consulta PostgreSQL.

### Qué hay hecho

- **`collector`** — dado un Riot ID: PUUID (ACCOUNT-V1), identificadores
  de las últimas partidas de ranked solo (MATCH-V5), y de cada una su detalle y su
  timeline. Guarda la partida, los diez participantes y los eventos de
  compra y de habilidades, sin duplicar. Antes de descargar consulta
  cuáles ya están en la base y se las salta, así que solo pide a Riot lo
  que le falta. Con reintentos ante fallos de red y control del límite de
  peticiones.
- **`db`** — cinco tablas en PostgreSQL, volumen con nombre para
  que los datos sobrevivan a los reinicios y arranque ordenado con
  healthcheck.
- **`flyway`** — aplica las migraciones pendientes al arrancar y termina.
  Los servicios que usan la base esperan a que acabe.
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

- Tests y CI
- Gráfica de winrate y comparar varios invocadores
- Copia de seguridad de la base de datos
- Despliegue en Kubernetes

## Requisitos

- Docker
- Una clave de la API de Riot: https://developer.riotgames.com
  La Development Key caduca cada 24 horas. Una personal key, que se pide
  registrando el proyecto en el portal, no caduca.

## Configuración

Copiar `.env.example` a `.env` y rellenar los valores:

```
RIOT_API_KEY=RGAPI-...
RIOT_GAME_NAME=TuNombre
RIOT_TAG_LINE=EUW

POSTGRES_USER=loltest
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

- `db`, `redis`, `api`, `frontend` y `scheduler` son procesos largos: se
  quedan corriendo hasta que se paran.
- `collector` y `flyway` terminan cuando acaban su trabajo. En
  `docker compose ps` aparecen como `Exited (0)`, que no es un error.

Qué comando usar según lo que hayas cambiado:

```bash
docker compose up            # docker-compose.yml, .env o una migración nueva
docker compose up --build    # el código o requirements.txt
```

El `--build` hace falta porque `collector.py`, `api.py`, `config.py` y
`requirements.txt` se copian dentro de la imagen. El `.env` y las
migraciones se leen al arrancar, así que esos no lo necesitan.

Va sin nombrar servicio. `collector`, `scheduler` y `api` comparten el
`Dockerfile`, pero Compose construye una imagen por servicio:
`docker compose up --build api` reconstruye solo esa y deja a las otras dos
con el código anterior, sin dar ningún error. Nombrar un servicio vale para
levantarlo suelto, no para reconstruir.

Los cambios de esquema ya no necesitan `down -v`: se escriben como una
migración nueva y `flyway` la aplica al arrancar, sin tocar los datos.
Ver [Migraciones](#migraciones).

## Base de datos

Cinco tablas:

- `summoners` — traduce cada PUUID a un Riot ID legible
- `matches` — fecha, duración, tipo de cola y parche de cada partida
- `participants` — los diez jugadores de cada partida: campeón, posición,
  KDA, resultado, oro, daño hecho y recibido, CS, visión, objetos finales,
  hechizos de invocador y equipo
- `item_purchases` — cada compra de cada jugador, con su minuto
- `skill_levelups` — cada subida de habilidad, con su minuto

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

### Solo ranked solo/duo

El `collector` pide a Riot únicamente los identificadores de esa cola:

```python
params={"count": MATCH_COUNT, "queue": RANKED_SOLO_QUEUE}
```

El filtro va en la petición y no al guardar, así que las partidas de otros
modos ni se descargan. Sin él, Riot devuelve las últimas partidas de
cualquier tipo y las normales y los swiftplay acaban mezclados con las
ranked, falseando todas las medias.

`RANKED_SOLO_QUEUE` está en `config.py` y no en el `.env` porque no es
configuración que cambie según el entorno. El proyecto entero se define
sobre esa cola, y cambiarla dejaría sin sentido lo que ya está guardado.

`matches.queue_id` se sigue guardando aunque hoy valga siempre 420, porque
es el dato tal como viene de Riot. La API no lo expone.

### Borrar partidas

Las claves ajenas hacia `matches` tienen `ON DELETE CASCADE`, así que
borrar una partida se lleva sus participantes, sus compras y sus subidas
de habilidad:

```sql
DELETE FROM matches WHERE queue_id <> 420;
```

Esa sentencia responde `DELETE 6` contando solo las filas de `matches`;
las de las otras tres tablas desaparecen sin aparecer en el mensaje. Con
seis partidas eso son unas 2.200 filas, así que conviene contar antes de
borrar.

La clave de `participants` hacia `summoners` no lleva cascade a propósito.
Quitar un invocador de los seguidos no debe borrar sus participaciones:
esas partidas siguen existiendo.

### Los diez jugadores

`participants` guarda a los diez de cada partida, no solo al invocador
propio. De los demás se guarda todo lo de la partida y **nada de su
identidad**: el PUUID solo se rellena para los invocadores seguidos.

La clave primaria es `(match_id, participant_id)`, el número de jugador
dentro de la partida (1-10), que existe siempre. Antes era
`(match_id, puuid)`, que dejaba fuera a quien no tuviera PUUID.

El `puuid` quedó opcional, y eso basta para que su referencia a `summoners`
no estorbe: en SQL, una clave ajena nula no se comprueba.

Para enseñar el marcador hace falta un `LEFT JOIN`; uno normal descartaría
las nueve filas sin PUUID:

```sql
SELECT p.team_id, p.champion, s.game_name,
       p.kills || '/' || p.deaths || '/' || p.assists AS kda
FROM participants p
LEFT JOIN summoners s ON s.puuid = p.puuid
WHERE p.match_id = 'EUW1_...'
ORDER BY p.team_id, p.participant_id;
```

Sale una fila con nombre y nueve sin él; esas se muestran con el nombre
del campeón. Al añadir un invocador a los seguidos, sus filas anteriores se
rellenan con un `--refetch`.

`team_id` es 100 (azul) o 200 (rojo), como lo da Riot. Separa aliados de
rivales y permite calcular la participación en asesinatos, que necesita las
kills de todo el equipo:

```sql
SELECT champion,
       ROUND(100.0 * (kills + assists)
             / NULLIF(SUM(kills) OVER (PARTITION BY team_id), 0), 1) AS kp_pct
FROM participants
WHERE match_id = 'EUW1_...'
ORDER BY kp_pct DESC;
```

El `SUM(...) OVER (PARTITION BY ...)` es una función de ventana: suma por
equipo sin agrupar las filas, así que cada jugador conserva la suya y ve
además el total.

Una clave primaria crea su índice automáticamente. La anterior,
`(match_id, puuid)`, servía además para buscar por `puuid`; la nueva no,
porque esa columna ya no está. Por eso `V6` crea `idx_participants_puuid`
aparte.

### El timeline

Los objetos finales (`item0`…`item6`) dicen cómo acabó la build, no en qué
orden se llegó ahí. El orden está en otro endpoint, el *timeline*, que es
una petición más por partida:

```
/lol/match/v5/matches/{id}          detalle    → matches, participants
/lol/match/v5/matches/{id}/timeline eventos    → item_purchases, skill_levelups
```

Viene partido en frames, uno por minuto, y cada frame trae sus eventos:
compras, muertes, torres, guardianes. De todos ellos se guardan dos tipos,
`ITEM_PURCHASED` y `SKILL_LEVEL_UP`, de los diez jugadores. Son unas 300 y
180 filas por partida.

La respuesta pesa cerca de 1 MB, así que no se guarda entera: extraer los
cuatro campos que importan la deja en unos 19 KB por partida, cincuenta
veces menos.

Tres cosas que hace el `collector` al procesarlo:

- **Descarta los eventos con `participantId` 0.** Los jugadores van del 1
  al 10; los del 0 son artefactos del arranque de la partida.
- **Aplica los `ITEM_UNDO`.** Comprar algo y deshacerlo en la tienda genera
  un evento de compra y otro de deshacer. Sin esto, el primer objeto de una
  build podría ser uno que se devolvió.
- **Borra antes de insertar.** La clave de estas tablas es un id
  automático, así que un `--refetch` duplicaría las filas en vez de
  reemplazarlas.

Los jugadores se identifican por su número dentro de la partida (1-10), no
por PUUID: para analizar builds basta, y así no se guarda la identidad de
nadie más. `participants.participant_id` guarda ese número para el propio
invocador, que es lo que permite filtrar sus compras:

```sql
SELECT ip.timestamp_ms / 60000 AS minuto, ip.item_id
FROM item_purchases ip
JOIN participants p
  ON p.match_id = ip.match_id AND p.participant_id = ip.participant_id
WHERE ip.match_id = 'EUW1_...'
ORDER BY ip.timestamp_ms;
```

Los `item_id` son números; la traducción a nombre e icono sale de Data
Dragon, igual que con los campeones. Se guarda el número porque si Riot
renombra un objeto, el historial no queda con un nombre que ya no existe.

Sobre lo que se puede concluir con estos datos: comparar winrates por
build necesita decenas de partidas en cada rama, y un parche dura dos
semanas. Con pocas partidas esos porcentajes no son fiables. El historial
propio sí vale ("con esta build llevo 12-4"), siempre que se enseñe sobre
cuántas partidas está calculado.

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

1. Escribir la migración con la columna nueva (`V6__...sql`)
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
  más antigua. Cruza `participants` con `matches` y devuelve identificador,
  campeón, posición, KDA, resultado, fecha, duración y parche, este último
  en las dos numeraciones: `game_version` tal como lo da Riot y `patch`
  como lo ve el jugador.
- `GET /champions` — un resumen por campeón: partidas jugadas, ganadas,
  winrate y KDA medio. Los agregados los calcula PostgreSQL con
  `GROUP BY`; ninguno de esos números está guardado en ninguna tabla.
- `GET /champions/{champion}` — lo mismo para un solo campeón. No
  distingue mayúsculas (`/champions/zeri` vale) y devuelve 404 si no hay
  partidas con ese campeón.

Todos los endpoints de datos filtran por `puuid IS NOT NULL`. `participants`
guarda a los diez jugadores de cada partida y solo los invocadores seguidos
tienen PUUID, así que sin ese filtro los agregados incluirían a rivales y
compañeros. Cuando haya varios invocadores seguidos habrá que añadir un
parámetro para elegir de cuál.

Al levantar `api`, Compose arranca antes `db`, `flyway` y `redis`: espera
al healthcheck de los dos primeros y a que `flyway` termine bien.

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
  "games": 6,
  "wins": 3,
  "winrate_pct": 50.0,
  "avg_kills": 9.3,
  "avg_deaths": 4.8,
  "avg_assists": 6.3
}
```

Una partida de `/matches`:

```json
{
  "match_id": "EUW1_7979729853",
  "champion": "Zeri",
  "position": "BOTTOM",
  "kills": 12,
  "deaths": 8,
  "assists": 7,
  "win": false,
  "played_at": "2026-09-09T22:14:03+02:00",
  "duration_seconds": 2520,
  "game_version": "16.17.810.4348",
  "patch": "26.17"
}
```

## Migraciones

El esquema de la base vive en `migrations/`, un fichero por cambio:

```
migrations/
  V1__initial_schema.sql               summoners, matches, participants
  V2__index_matches_played_at.sql      índice para el ORDER BY de /matches
  V3__participant_match_details.sql    oro, daño, CS, visión, objetos
  V4__timeline_events.sql              item_purchases y skill_levelups
  V5__participants_participant_id.sql  el número de jugador (1-10)
  V6__all_ten_participants.sql         los diez jugadores y la clave nueva
```

El nombre es la convención de Flyway: `V`, el número, **dos** guiones
bajos y la descripción. Con un solo guion el fichero se ignora.

Cada fichero lleva solo su cambio, no el esquema entero. El estado de la
base es el resultado de aplicarlos todos en orden.

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

El motivo: si se editara una migración que lleva meses aplicada en
producción, un entorno nuevo ejecutaría la versión corregida y producción
se quedaría con la vieja, sin avisar a nadie. Para corregir algo se escribe
la migración siguiente.

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
estáticos con un servidor web dedicado es lo estándar, y permite añadir un
reverse proxy delante más adelante.

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

Solo se autoriza el método `GET`, que es lo único que hace la API.

CORS no protege la API: `curl` y cualquier cosa que no sea un navegador
acceden igual. Lo que evita es que una página de otro origen lea respuestas
aprovechando la sesión del usuario.

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

## Tests

Los tests viven en `test_api.py` y se lanzan con pytest desde el entorno
virtual:

```bash
source .venv/bin/activate
pytest
```

Las herramientas de test están en `requirements-dev.txt`, separado de
`requirements.txt` porque este último se instala dentro de la imagen y la
aplicación no necesita pytest para funcionar. Para tener el entorno local
completo:

```bash
pip install -r requirements.txt -r requirements-dev.txt
```

### Cómo funcionan

`TestClient` de FastAPI llama a los endpoints sin levantar uvicorn y sin
abrir ningún puerto: importa `api.py` y ejecuta las funciones de ruta
directamente. Por eso tardan milisegundos y no hace falta tener nada
arrancado.

Importar `api.py` ejecuta el módulo entero, así que un test que solo mira
`/health` ya comprueba de paso que `config.py` encuentra sus variables, que
el logging se configura y que las cuatro rutas se registran.

Pytest busca ficheros que empiecen por `test_` y, dentro, funciones que
empiecen por `test_`. Una función con otro nombre no se ejecuta y no avisa
de nada.

### Qué cubren y qué no

Hoy solo se prueba `/health`, que no consulta PostgreSQL ni Redis. Los
endpoints que sí leen de la base necesitan datos controlados y una base
propia, no las partidas que haya guardadas en ese momento.

Estos tests tampoco comprueban que la imagen se construya, que uvicorn
arranque ni que los puertos estén publicados. Eso es trabajo del pipeline.

El `.venv` usa la misma versión de Python que la imagen (3.14). Si se
separan, un test puede pasar en local y fallar en el pipeline.

## Estructura

```
test_api.py          los tests de la API                  → se lanzan con pytest
collector.py         baja partidas de Riot y las guarda   → servicio collector
api.py               sirve lo guardado, cuatro endpoints   → servicio api
config.py            la configuración, en un solo sitio    → lo importan los dos
migrations/          el esquema, versionado paso a paso    → servicio flyway
frontend/index.html  la página que consume la API          → servicio frontend
frontend/borrador/   notas para trabajar el diseño aparte
Dockerfile           la imagen de collector, scheduler y api
docker-compose.yml   los siete servicios, el volumen y los healthchecks
requirements.txt     dependencias de Python, con versiones fijadas
requirements-dev.txt pytest y compañía, fuera de la imagen
.env                 los valores reales (fuera del repo y de la imagen)
.env.example         las mismas claves, sin valores
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

`config.py` centraliza la lectura del `.env`. `collector.py` y `api.py`
importan de ahí en vez de construir cada uno su cadena de conexión.

Las variables sin valor por defecto pasan por `obligatoria()`, que corta la
ejecución con un mensaje claro si faltan. Sin eso, una variable ausente se
cuela como el texto `None` dentro de la cadena de conexión y el fallo
aparece más tarde, al conectar, diciendo que la contraseña es incorrecta
cuando lo que pasa es que no hay ninguna.

El logging se configura en `config.py` y no en cada script. `config.py` es
lo primero que importan `collector.py` y `api.py`, así que cuando el resto
del código escribe su primer mensaje el formato ya está puesto. Hace falta
configurarlo porque uvicorn solo ajusta sus propios loggers.

`scheduler` usa la misma imagen que `collector` y lo único que cambia es el
comando: un bucle de shell que ejecuta `collector.py` y duerme. Como el
script en sí no contiene nada del bucle, al desplegar en Kubernetes se puede
sustituir por un CronJob sin tocar el código.

Redis es opcional por diseño. Las llamadas a la caché van envueltas en
`cache_get` y `cache_set`, que capturan cualquier error y lo tratan como
"no hay nada cacheado": la API responde igual, más lenta, y deja un aviso
en los logs. El cliente lleva además `socket_timeout=1`, para que un Redis
que acepta la conexión pero no contesta no deje la petición esperando.

`game_version` es la numeración interna de Riot, la que da la API. No
coincide con la que ve el jugador en el cliente: la pública va diez por
delante en el primer número (interna `16.17` = pública `26.17`), porque
cada serie interna corresponde a un año natural. El campo `patch` de
`/matches` hace esa conversión al vuelo; en la base solo se guarda el
valor original.

Los porcentajes viajan como números (`winrate_pct: 66.7`), sin el símbolo.
Del formato se encarga quien los muestra.

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

- Un pool de conexiones en la API. Hoy cada endpoint abre su propia
  conexión a PostgreSQL y la cierra al terminar, y abrir una conexión es de
  lo más caro que hay. Con un usuario no se nota; con varias réplicas, sí.
  `psycopg` trae uno. Aplazado hasta tener tests que comprueben que las
  respuestas no cambian.
- Invalidar la caché desde el `collector` cuando guarde partidas nuevas, en
  vez de esperar a que caduque el TTL.
- `/health` no lo consulta nadie. El servicio `api` no tiene healthcheck en
  el compose, así que el endpoint existe pero solo lo llaman los tests y las
  comprobaciones a mano. Al desplegar en Kubernetes hará falta separarlo en
  dos: `/health` respondiendo siempre, sin comprobar nada, para saber si el
  proceso vive; y `/ready` comprobando PostgreSQL, para saber si puede
  atender peticiones. Si la base se cae, lo que hay que hacer es dejar de
  mandarle tráfico, no reiniciar contenedores que están sanos.
- Decidir si `/docs` y `/redoc` se desactivan al desplegar fuera de local.
  Se hace con `docs_url=None` al crear la aplicación.
- Los contenedores del Dockerfile corren como root. La imagen base de Python
  no trae usuario propio y nunca se añadió uno, así que `collector`,
  `scheduler` y `api` arrancan con todos los permisos dentro del contenedor.
  Se arregla creando un usuario sin privilegios y poniendo `USER` después del
  `pip install`, que sí necesita root. Las otras tres imágenes son oficiales
  y ya se bajan a su propio usuario.
