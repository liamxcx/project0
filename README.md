# Project 0

Herramienta personal de estadísticas de League of Legends.
Consume la API de Riot Games y guarda el historial de partidas en PostgreSQL.

Proyecto de aprendizaje: el objetivo es llegar a una aplicación
contenerizada con base de datos, API propia y frontend.

Solo se procesan partidas de Ranked Solo/Duo (queueId 420).

## Estado actual

El `collector`, base de datos con migraciones, API propia, una página que la
consume y tests que se ejecutan en cada push, todo funcionando en Compose.
El despliegue en Kubernetes está en marcha: la API, Redis, PostgreSQL y el
`collector` ya corren en un clúster local con kind (ver [Kubernetes](#kubernetes)).

### Cómo encajan las piezas

Al arrancar Compose, `flyway` pone el esquema al día y solo entonces
arrancan los servicios que usan la base:

```
db ──sano──▶ flyway ──termina──▶ collector / api
```

En el clúster, un CronJob lanza el `collector` cada hora para traer las
partidas nuevas de Riot:

```
CronJob collector  ──cada hora──▶  pod collector  ──▶  API de Riot
                                        │              detalle de la partida
                                        │              y su timeline
                                        └──▶  PostgreSQL
```

Cuando alguien abre la página en Compose, el navegador pide la página al
`frontend` y los datos a la `api`:

```
navegador  ──▶  frontend   :8080   la página (nginx, ficheros estáticos)
     │
     └────────▶  api       :8000  ──▶  Redis        ¿está cacheada?
                                  └──▶  PostgreSQL   solo si no lo está
```

Son dos puertos distintos, o sea dos orígenes distintos, y por eso la API
tiene que autorizar al frontend (ver CORS).

`collector` arranca, descarga, guarda y termina. En el clúster lo lanza un
CronJob cada hora. En Compose se ejecuta una vez al hacer `up`, y después a
mano con `docker compose run --rm collector`. `db`, `redis`, `api` y
`frontend` se quedan en marcha.

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
- **`api`** — cinco endpoints con FastAPI, agregados calculados en SQL y
  documentación interactiva automática en `/docs`.
- **`redis`** — caché de respuestas de la API, con caducidad automática y
  opcional: si Redis no responde, la API consulta PostgreSQL y sigue
  funcionando.
- **`frontend`** — nginx sirviendo una página estática que pide los datos
  a la API desde el navegador.
- **Tests** — pytest sobre los cinco endpoints y la caché, contra un
  PostgreSQL y un Redis propios, con datos inventados.
- **CI** — GitHub Actions pasa Ruff, ejecuta los tests y construye las
  imágenes en cada push, y marca cada commit en verde o en rojo. En `main`
  sube además las imágenes a GitHub Container Registry.
- **Kubernetes** — la API con dos réplicas, Redis, PostgreSQL y el
  `collector`, que un CronJob lanza cada hora, en un clúster local con kind.
  Las imágenes salen del CI, el esquema lo aplica un Job y los datos de
  PostgreSQL viven en un disco que se conserva.

### Qué falta

- Gráfica de winrate y comparar varios invocadores
- Copia de seguridad automática de la base de datos
- Llevar el frontend a Kubernetes

## Requisitos

- Docker
- kind y kubectl, para el clúster local de Kubernetes
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

`CACHE_TTL_SECONDS` es cuántos segundos vive cada respuesta cacheada. Es
el desfase máximo entre lo que hay en PostgreSQL y lo que devuelve la API.
Subirlo alivia a PostgreSQL a costa de servir datos más viejos.

`CORS_ORIGINS` son los orígenes que pueden leer las respuestas de la API
desde un navegador. Varios se separan por comas, y van sin barra final.
Cambia según dónde se despliegue, por eso es configuración y no código.

`DB_HOST` es `db` dentro de Compose. En el clúster es `postgres` y lo pone
el ConfigMap `project0-config`. Para ejecutar el script fuera de Docker hay
que ponerlo a `localhost`.

`DB_PORT` no va en el `.env` y vale 5432 si falta. Solo lo cambian los
tests, que usan su propia base en el 5433.

## Ejecución

```bash
docker compose up
```

Levanta los seis servicios. El esquema lo aplica `flyway` antes de que
arranquen `collector` y `api`.

Los servicios no se comportan igual:

- `db`, `redis`, `api` y `frontend` son procesos largos: se quedan
  corriendo hasta que se paran.
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

Va sin nombrar servicio. `collector` y `api` comparten el `Dockerfile`,
pero Compose construye una imagen por servicio:
`docker compose up --build api` reconstruye solo esa y deja la otra con el
código anterior, sin dar ningún error. Nombrar un servicio vale para
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
ids_response = fetch(
    f"{RIOT_BASE_URL}/lol/match/v5/matches/by-puuid/{puuid}/ids",
    params={"count": MATCH_COUNT, "queue": RANKED_SOLO_QUEUE},
)
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
- `GET /ready` — devuelve `{"estado": "listo"}` si PostgreSQL responde a un
  `SELECT 1`, y un 503 si no. En Kubernetes, `/health` es la liveness probe
  y `/ready` la readiness probe.
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

`/health` y `/ready` no se cachean. Y las respuestas vacías
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
  V7__cascade_on_match_delete.sql      borrar una partida borra sus filas
```

El nombre es la convención de Flyway: `V`, el número, **dos** guiones
bajos y la descripción. Con un solo guion el fichero se ignora.

Cada fichero lleva solo su cambio, no el esquema entero. El estado de la
base es el resultado de aplicarlos todos en orden.

### Cómo se aplican

El servicio `flyway` se ejecuta al arrancar, aplica lo que falte y
termina. `collector` y `api` esperan a que acabe bien
(`service_completed_successfully`), así que si una migración falla la
aplicación no arranca, en vez de trabajar sobre una base a medias.

Flyway lleva la cuenta en una tabla de la propia base,
`flyway_schema_history`, que se puede consultar como cualquier otra.

En el clúster las aplica el Job `migrations`, con una imagen de Flyway que
lleva los `.sql` dentro (ver [Desplegar una versión nueva](#desplegar-una-versión-nueva)).

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

### Meter Flyway en una base que ya existe

Si la base ya tiene las tablas, `migrate` intentaría ejecutar la V1 y
fallaría. Para eso está `flyway baseline -baselineVersion=1`, que crea la
tabla de control y apunta la V1 como aplicada sin ejecutarla. Desde ahí,
`migrate` sigue con la V2.

Se usó al montar Flyway, sobre la base con partidas de entonces. La base
actual se reconstruyó después desde cero, así que en
`flyway_schema_history` la V1 sale como `SQL` y no como `BASELINE`.

## Copia de seguridad

```bash
mkdir -p backups
docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > backups/project0-$(date +%F).dump
```

Para restaurarla en una base vacía:

```bash
docker compose exec -T db sh -c 'pg_restore -U "$POSTGRES_USER" -d <base>' < backups/<fichero>.dump
```

Para restaurarla en el clúster, sustituyendo lo que haya en `postgres-0`, y
aplicar después las migraciones escritas desde la copia:

```bash
kubectl exec -i postgres-0 -- sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --single-transaction' < backups/<fichero>.dump
kubectl delete job migrations
kubectl apply -f k8s/migrations-job.yaml
```

`--clean --if-exists` borra cada objeto de la copia antes de crearlo, y
`--single-transaction` hace que, si algo falla, la base se quede como
estaba.

La copia va en formato custom de `pg_dump` y la carpeta `backups/` está
fuera de Git. Se hace a mano. La copia automática llegará con Kubernetes.

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
2026-09-09 03:42:50  WARNING  No se ha podido leer champions:all de Redis: Error -2 connecting to redis:6379. Name or service not known.
```

Los niveles: `INFO` para el curso normal, `WARNING` para lo que va mal pero
no impide seguir (un reintento, Redis caído), y `ERROR` para lo que corta la
ejecución (clave caducada, API inalcanzable).

```bash
docker compose logs -f api                    # seguir en directo
docker compose logs --tail 20 api             # las últimas 20 líneas
docker compose logs --since 3h api            # las últimas 3 horas
docker compose logs collector | grep WARNING  # solo los problemas
```

El `Dockerfile` define `PYTHONUNBUFFERED=1`. Sin eso Python acumula la
salida en un buffer y la suelta al terminar, así que los mensajes de un
servicio que no termina nunca, como `api`, llegarían tarde.

Los logs se rotan para que no crezcan sin límite: cada servicio guarda
como mucho 3 ficheros de 10 MB, y al abrir el cuarto se borra el más
viejo. Son 30 MB por servicio como techo. Sin esto un servicio que no
termina nunca, como `api`, acabaría llenando el disco.

La configuración está en el bloque `x-logging` del `docker-compose.yml`,
y cada servicio la referencia con `logging: *default-logging`. Los
cambios ahí solo afectan a contenedores nuevos:

```bash
docker compose up -d --force-recreate
docker inspect project0-api-1 --format '{{json .HostConfig.LogConfig}}'
```

## Tests

Los tests viven en `test_api.py` y usan su propia base de datos y su
propio Redis, que se levantan aparte con `docker-compose.test.yml`:

```bash
docker compose -f docker-compose.test.yml up -d
source .venv/bin/activate
pytest
```

Los contenedores se quedan levantados entre ejecuciones, así que el primer
comando solo hace falta una vez. Sin ellos, `/health` pasa igual y el resto
falla con un error de conexión al puerto 5433 o al 6380. Para tirarlos al
acabar:

```bash
docker compose -f docker-compose.test.yml down
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
directamente. Por eso tardan milisegundos. Lo único que tiene que estar
arrancado son la base y el Redis de test.

Importar `api.py` ejecuta el módulo entero, así que un test que solo mira
`/health` ya comprueba de paso que `config.py` encuentra sus variables, que
el logging se configura y que las rutas se registran.

Pytest busca ficheros que empiecen por `test_` y, dentro, funciones que
empiecen por `test_`. Una función con otro nombre no se ejecuta y no avisa
de nada.

### Los contenedores de test

`docker-compose.test.yml` levanta un PostgreSQL (`db-test`) y un Flyway
(`flyway-test`) que le aplica las mismas migraciones que a la base de
verdad. Es un proyecto de Compose aparte, `project0-test`, así que no sale
en el `docker compose ps` de siempre ni se levanta con el `up` normal.

La base se publica en el 5433 porque el 5432 lo tiene la base real, y no
tiene volumen. Al tirarla se pierde todo y la siguiente vez arranca vacía.

Las credenciales (`test`/`test`/`test`) están escritas en el propio
fichero en vez de salir del `.env`. La base es desechable y solo escucha
en localhost, y así funciona igual donde no haya `.env`, como en el
pipeline.

También levanta `redis-test`, con la misma imagen que el Redis del
proyecto y sin contraseña, igual que él. Se publica en el 6380 para que
no choque con otro Redis que haya en la máquina.

### conftest.py

pytest ejecuta `conftest.py` antes de cargar los tests. Ahí se hacen tres
cosas.

Se ponen `DB_HOST`, `DB_PORT` y las credenciales apuntando a `db-test`, y
`REDIS_URL` apuntando a `redis-test`. Como `load_dotenv()` no sobrescribe
variables que ya existen, cuando `config.py` monta `DB_URL` sale
`postgresql://test:test@localhost:5433/test` y no la base real. El resto
de variables que usa la API tienen valor por defecto, así que los tests no
necesitan un `.env`.

La fixture `seeded_db` vacía las tablas, mete tres partidas inventadas y las
vuelve a vaciar al acabar el test, pase o falle. Los tests que la
necesitan la piden como parámetro. Son pocos datos a propósito, para que
el resultado esperado de cada test se pueda contar a mano.

La fixture `disable_cache` se aplica sola a todos los tests y cambia
`cache_get` y `cache_set` por funciones que no hacen nada, así que la API
va siempre a la base. Si no, un test podría recibir la respuesta que dejó
cacheada el anterior.

Los tests que sí quieren la caché llevan encima `@pytest.mark.with_cache`.
Con esa marca, `disable_cache` no toca nada y la API usa `redis-test` de
verdad. Además vacía Redis antes y después del test, por lo mismo que
`seeded_db` vacía la base. La marca se registra en `pytest_configure`, porque
si no pytest avisa de que no la conoce.

Está hecho así, y no al revés, para que olvidar la marca no tenga
consecuencias. Un test sin ella lee de la base como los demás. Si la
caché estuviera encendida por defecto, un test que se olvidara de
apagarla dependería de lo que hubiera dejado en Redis el anterior.

### Qué cubren y qué no

Los cinco endpoints tienen al menos un test. `/ready` tiene dos: uno con la
base de test, que debe dar 200, y otro que apunta la conexión a un puerto
donde no escucha nadie, que debe dar 503. Entre los datos hay rivales
sin `puuid`, uno de ellos con un campeón que también lleva el invocador,
así que si el filtro de la API se rompe se nota en `/matches`, en
`/champions` y en `/champions/{champion}`.

Dos tests más comprueban la caché. El primero llama a `/matches`, borra
las partidas de la base y vuelve a llamar. Si la segunda respuesta sigue
trayendo las tres partidas, es que ha salido de Redis. El segundo cambia
el cliente de Redis de la API por uno que apunta a un puerto donde no
escucha nadie, y comprueba que `/matches` responde igual desde la base.
Si alguien quita el `try/except` de `cache_get`, ese test falla.

Estos tests no usan el `Dockerfile`. Que la imagen se construya lo
comprueba el job `build` del pipeline. Que uvicorn arranque dentro del
contenedor y que los puertos estén publicados no lo comprueba nada todavía.

El `.venv` usa la misma versión de Python que la imagen (3.14). Si se
separan, un test puede pasar en local y fallar en el pipeline.

## CI

Cada push a GitHub ejecuta el pipeline de CI (integración continua) en
GitHub Actions. El workflow está en `.github/workflows/ci.yml` y el
resultado sale al lado de cada commit, con un tick verde si todo pasa y una
cruz roja si algo falla. El detalle de cada ejecución está en la pestaña
Actions del repositorio.

Se dispara con un push a cualquier rama, no solo a `main`. Así se puede
probar un cambio en una rama aparte sin que llegue a `main`.

El workflow tiene tres jobs, `lint`, `tests` y `build`. Arrancan a la vez,
cada uno en su propia máquina Ubuntu que GitHub borra al acabar. Que falle
uno no para a los otros, así que un fallo de formato no esconde si los
tests pasan.

Dentro de un job, si un paso termina con error, los siguientes no se
ejecutan. Para saber qué ha fallado hay que abrir el job en rojo y mirar
qué paso tiene la cruz.

### lint

Instala `requirements-dev.txt` y pasa Ruff en dos pasos:

```bash
ruff format --check .
ruff check .
```

El primero comprueba que el código tiene el formato de Ruff, sin cambiar
nada. El segundo pasa el linter, que busca imports sin usar, variables que
no se usan y fallos parecidos. Van separados para ver a la primera cuál de
los dos ha fallado.

Ruff está fijado en `requirements-dev.txt` para que el pipeline y cualquier
máquina usen la misma versión. La extensión del editor puede traer otra, y
entre versiones cambian las reglas de formato.

Para dejar el código como lo quiere Ruff antes de un commit:

```bash
ruff format .
```

Ruff también formatea los bloques de Python de este README, así que lo que
vaya en un bloque ```` ```python ```` tiene que ser Python válido.

### tests

Los mismos pasos que en local:

1. Clonar el repositorio (`actions/checkout`).
2. Instalar Python 3.14 (`actions/setup-python`), la misma versión que la
   imagen y el `.venv`.
3. Instalar `requirements.txt` y `requirements-dev.txt`.
4. Levantar los contenedores de test y aplicar las migraciones.
5. Lanzar `pytest -v`.

La cruz puede venir de una dependencia que no se instala o de una
migración que falla, no solo de un test.

### Los contenedores en el pipeline

Se levantan con el mismo `docker-compose.test.yml` que en local, así que
los dos prueban contra lo mismo y la configuración está en un solo sitio.
GitHub Actions tiene su propia forma de declarar contenedores
(`services:`), pero habría que repetir ahí la imagen, los puertos y los
healthchecks, y no sirve para contenedores que terminan, como
`flyway-test`.

Se hace en dos comandos:

```bash
docker compose -f docker-compose.test.yml up -d --wait db-test redis-test
docker compose -f docker-compose.test.yml run --rm flyway-test
```

`--wait` no devuelve el control hasta que los healthchecks de `db-test` y
`redis-test` dan bien. Sin él, los tests podrían empezar antes de que
Redis aceptara conexiones.

`flyway-test` va aparte porque `--wait` trata como un fallo que un
contenedor termine, aunque acabe con código 0. `run` lo ejecuta en primer
plano, espera a que acabe y devuelve su código de salida, así que si una
migración falla el paso falla y no se llega a los tests. `--rm` borra el
contenedor al terminar.

Los mismos dos comandos sirven en local en lugar del `up -d` de la sección
Tests.

### Sin .env ni secretos

En el pipeline no hay `.env`, y no hace falta. `conftest.py` pone las
variables de la base y de Redis, y la API no exige ninguna más. Las de Riot
solo las exige `collector.py` (ver Notas), y los tests no lo ejecutan. Por
eso no hay ninguna clave de Riot guardada en GitHub.

### build

Construye las dos imágenes del proyecto con las acciones oficiales de
Docker (`docker/setup-buildx-action` y `docker/build-push-action`). Es un
`matrix`: el job se escribe una vez y GitHub lanza una copia por imagen, a
la vez:

```
build (api)          Dockerfile              ghcr.io/liamxcx/project0
build (migrations)   migrations/Dockerfile   ghcr.io/liamxcx/project0-migrations
```

Hace falta porque los tests ejecutan el código directamente y nunca usan el
`Dockerfile`, así que un `COPY` de un fichero que no existe o un
`pip install` que falla dentro de la imagen no saldría en ningún otro
sitio.

En `main` las construye para amd64 y arm64 y las sube a GitHub Container
Registry, etiquetadas con el SHA corto del commit. Las dos llevan el mismo
tag, así que se sabe qué migraciones van con qué código. En el resto de
ramas solo las construye para amd64 y no las sube, así que el aviso
`No output specified with docker-container driver` del log es esperado.
Las capas se guardan en la caché de Actions para no reconstruir lo que no
ha cambiado.

`build` solo arranca si `lint` y `tests` pasan, para no subir nunca una
imagen con código que no los pasa. Si falla una de las dos copias, GitHub
cancela la otra.

`build-push-action` guarda además un registro del build como artifact de la
ejecución. Se puede descargar e importar en la sección Builds de Docker
Desktop para ver el build paso a paso.

### El sistema del runner

Los tres jobs usan `ubuntu-latest`, que GitHub mueve a la siguiente
versión LTS cuando sale. Se deja así porque del sistema solo se usa Docker.
Python lo instala `setup-python` en la versión indicada y lo demás va en
contenedores con la imagen fijada.

## Kubernetes

Clúster local con kind, definido en `kind-config.yaml`: un control plane y
dos workers.

```bash
kind create cluster --config kind-config.yaml   # crearlo
kubectl get nodes                               # los tres nodos en Ready
kind delete cluster --name project0             # borrarlo
```

El primer worker publica el 80 y el 443 en `127.0.0.1` para el Ingress.
Los puertos solo se fijan al crear el clúster, así que cambiar
`kind-config.yaml` obliga a borrarlo y crearlo otra vez, y se pierde lo que
haya dentro.

### Desplegar

Los manifiestos están en `k8s/`. Las credenciales no están en el repo y van
en Secrets que se crean a mano, después del namespace y antes del resto:

```bash
kubectl apply -f k8s/00-namespace.yaml

read -rs GHCR_TOKEN
kubectl create secret docker-registry ghcr-pull -n project0 \
  --docker-server=ghcr.io --docker-username=<usuario de GitHub> \
  --docker-password="$GHCR_TOKEN"

kubectl create secret generic db-credentials -n project0 \
  --from-literal=POSTGRES_PASSWORD="$(grep '^POSTGRES_PASSWORD=' .env | cut -d= -f2-)"

kubectl create secret generic riot-credentials -n project0 \
  --from-literal=RIOT_API_KEY="$(grep '^RIOT_API_KEY=' .env | cut -d= -f2-)"

kubectl apply -f k8s/
```

El token es un token classic de GitHub con solo el permiso
`read:packages`.

En el clúster, la configuración que no es secreta no sale del `.env`, sino de
los ConfigMaps de `k8s/`. Tras cambiar uno, los pods no lo ven hasta que se
recrean:

```bash
kubectl rollout restart deployment/api
```

El `collector` no lo necesita, porque cada ejecución es un pod nuevo.

En un clúster nuevo PostgreSQL arranca vacío, así que el Job `migrations`
crea el esquema y los datos se traen restaurando una copia (ver
[Copia de seguridad](#copia-de-seguridad)).

Para probar la API desde fuera del clúster (el 8000 lo ocupa Compose):

```bash
kubectl get pods                              # api (dos), redis y postgres-0 en 1/1
kubectl port-forward service/api 8001:80      # y en otra terminal:
curl localhost:8001/ready
```

### Desplegar una versión nueva

Cada push a `main` sube las dos imágenes con el SHA corto del commit. Para
desplegarlas, se pone ese tag en el `image:` de `k8s/migrations-job.yaml`,
`k8s/api-deployment.yaml` y `k8s/collector-cronjob.yaml`, y:

```bash
kubectl delete job migrations                 # el spec de un Job no se puede cambiar
kubectl apply -f k8s/migrations-job.yaml
kubectl wait --for=condition=complete job/migrations --timeout=5m
kubectl diff -f k8s/                          # qué va a cambiar
kubectl apply -f k8s/
kubectl rollout status deployment/api         # espera al rolling update
```

El CronJob usa la imagen nueva desde su siguiente ejecución.

Las migraciones van primero porque el código nuevo puede necesitar una
columna nueva. Si el Job falla, la migración que falla se deshace y la API
se queda como estaba. El motivo está en `kubectl logs job/migrations`.

El commit del YAML se hace después de comprobar que funciona, para que lo
que hay en `main` coincida siempre con lo desplegado.

Si el despliegue no termina, los pods viejos siguen atendiendo hasta que el
nuevo pasa la readiness. Para ver qué falla y volver a la versión del
último commit:

```bash
kubectl get pods
kubectl describe pod <pod nuevo>              # los eventos, al final
git restore k8s/api-deployment.yaml
kubectl apply -f k8s/
```

### PostgreSQL

Corre en un StatefulSet con una réplica, y no en un Deployment, porque
necesita un disco propio que vuelva con él. El pod se llama siempre
`postgres-0` y su disco es el PVC `datos-postgres-0`, que el StatefulSet
crea a partir de `volumeClaimTemplates`. Si se borra el pod, vuelve con el
mismo nombre y el mismo disco, aunque con otra IP.

El disco usa la StorageClass `standard-retain`, definida en
`k8s/01-storageclass.yaml`. Es igual que la `standard` de kind, pero con
`reclaimPolicy: Retain`. Con la de kind, borrar el PVC borraría también los
datos. Con esta, el PV queda en `Released` y los datos siguen en el nodo
hasta que alguien los borre a mano. Ninguna de las dos sobrevive a
`kind delete cluster`, y para eso está la copia.

El Service `postgres` es headless (`clusterIP: None`). El DNS devuelve la
IP del pod en vez de una IP virtual, y cada pod tiene su propio nombre,
como `postgres-0.postgres`. Con una réplica no cambia nada, pero es lo que
permite añadir réplicas y que los clientes elijan a cuál conectarse.

Con una sola réplica, cada reinicio del pod es un corte. Al borrar
`postgres-0` con la API sirviendo, `/ready` respondió 503 durante unos dos
segundos y luego volvió solo.

### Collector

Lo lanza el CronJob `collector` cada hora en punto, en hora de Madrid. Cada
ejecución es un Job con su pod, que descarga las partidas nuevas, las guarda
y termina. Una hora basta porque las partidas no aparecen más rápido, y como
el `collector` no vuelve a pedir las que ya tiene, ejecutarlo más a menudo
tampoco gastaría peticiones de más.

```bash
kubectl get cronjob collector                 # horario y última ejecución
kubectl get jobs                              # una por hora, Complete o Failed
kubectl logs -l app.kubernetes.io/name=collector --prefix --tail=-1
kubectl create job collector-manual --from=cronjob/collector   # ejecutarlo ya
```

Se guardan los Jobs, con sus logs, de las 3 últimas ejecuciones buenas y de
las 3 últimas fallidas. Un Job `Complete` no asegura que se guardaran todas
las partidas. Si una falla, el `collector` la salta, termina bien y la vuelve
a intentar en la ejecución siguiente, así que el fallo solo queda en los logs.

Cuando algo va mal:

- No corren dos a la vez. Si una ejecución sigue en marcha a la hora
  siguiente, la nueva se lanza cuando acabe la anterior, o se salta si han
  pasado más de 30 minutos.
- Si el clúster estuvo parado, al arrancar lanza solo la última ejecución
  perdida, y solo si no han pasado más de 30 minutos desde su hora.
- Si termina con error se reintenta una vez, y si pasa de 10 minutos se
  corta.

Cada ejecución mira las últimas `MATCH_COUNT` partidas (20, en el ConfigMap
`collector-config`). Si se juegan más con el clúster parado, las más
antiguas se recuperan lanzándolo a mano con un `MATCH_COUNT` más alto.

## Estructura

```
test_api.py             los tests de la API                  → se lanzan con pytest
conftest.py             prepara la base y los datos de test
collector.py            baja partidas de Riot y las guarda   → servicio collector
api.py                  sirve lo guardado, cinco endpoints    → servicio api
config.py               la configuración, en un solo sitio    → lo importan los dos
migrations/             el esquema, versionado paso a paso    → servicio flyway y Job migrations
migrations/Dockerfile   la imagen de migraciones para el clúster
frontend/index.html     la página que consume la API          → servicio frontend
frontend/borrador/      notas para trabajar el diseño aparte
Dockerfile              la imagen de collector y api
docker-compose.yml      los seis servicios, el volumen y los healthchecks
docker-compose.test.yml la base y el Redis de test, aparte
kind-config.yaml        el clúster local de Kubernetes       → kind create cluster
k8s/                    los manifiestos del clúster           → kubectl apply -f k8s/
requirements.txt        dependencias de Python, con versiones fijadas
requirements-dev.txt    pytest, Ruff y compañía, fuera de la imagen
.github/workflows/      el pipeline de GitHub Actions         → se ejecuta en cada push
backups/                copias de la base con pg_dump (fuera del repo)
.env                    los valores reales (fuera del repo y de la imagen)
.env.example            las mismas claves, sin valores
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

Las tres variables de Riot son la excepción y se leen en `collector.py`.
Importar `config.py` ejecuta el fichero entero, así que si estuvieran ahí la
API no arrancaría sin ellas aunque no las use. Tampoco podrían lanzarse los
tests sin un `.env`.

Las variables sin valor por defecto pasan por `required_env()`, que corta la
ejecución con un mensaje claro si faltan. Sin eso, una variable ausente se
cuela como el texto `None` dentro de la cadena de conexión y el fallo
aparece más tarde, al conectar, diciendo que la contraseña es incorrecta
cuando lo que pasa es que no hay ninguna.

El logging se configura en `config.py` y no en cada script. `config.py` es
lo primero que importan `collector.py` y `api.py`, así que cuando el resto
del código escribe su primer mensaje el formato ya está puesto. Hace falta
configurarlo porque uvicorn solo ajusta sus propios loggers.

`collector.py` no contiene ningún bucle: arranca, descarga, guarda y
termina. Lo repite quien lo lanza, que en el clúster es un CronJob. Por eso
el bucle de shell que había en Compose se pudo sustituir sin tocar el
código.

Redis es opcional por diseño. Las llamadas a la caché van envueltas en
`cache_get` y `cache_set`, que capturan cualquier error y lo tratan como
"no hay nada cacheado": la API responde igual, más lenta, y deja un aviso
en los logs. El cliente lleva además `socket_timeout=1`, para que un Redis
que acepta la conexión pero no contesta no deje la petición esperando.
Un test comprueba que la API responde con Redis caído (ver [Tests](#tests)).

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

El código, las tablas, las columnas y las rutas están en inglés; los
mensajes de la consola, los comentarios y esta documentación, en español.

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
- Decidir si `/docs` y `/redoc` se desactivan al desplegar fuera de local.
  Se hace con `docs_url=None` al crear la aplicación.
- Los contenedores del Dockerfile corren como root. La imagen base de Python
  no trae usuario propio y nunca se añadió uno, así que `collector` y `api`
  arrancan con todos los permisos dentro del contenedor.
  Se arregla creando un usuario sin privilegios y poniendo `USER` después del
  `pip install`, que sí necesita root. Las otras tres imágenes son oficiales
  y ya se bajan a su propio usuario.
- El `collector` no atiende SIGTERM. Es el PID 1 de su contenedor y Python no
  prepara nada para esa señal, así que la ignora. Al pararlo, con
  `kubectl delete`, por el tope de 10 minutos o al vaciar un nodo, espera
  los 30 s de gracia y muere con SIGKILL, con código 137, que se confunde
  con un `OOMKilled`. No se pierden datos, porque la partida a medias se
  deshace. Se arregla saliendo del programa al recibir `signal.SIGTERM`.
