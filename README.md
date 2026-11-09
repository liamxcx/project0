# Project 0

Herramienta personal de estadísticas de League of Legends.
Consume la API de Riot Games y guarda el historial de partidas en PostgreSQL.

Proyecto para aprender DevOps con una aplicación real: contenedores con
Docker y Compose, CI con GitHub Actions y despliegue en Kubernetes con Helm.

Solo se procesan partidas de Ranked Solo/Duo (queueId 420).

## Estado actual

El `collector`, base de datos con migraciones, API propia, una página que la
consume y tests que se ejecutan en cada push. Todo corre en un clúster local
de Kubernetes con kind, instalado con un chart de Helm propio, y la página se
abre en `http://localhost`, entrando por Traefik (ver
[Kubernetes](#kubernetes)). Compose se queda como entorno de desarrollo.

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

Cuando alguien abre la página, todo entra por una sola puerta: Traefik en el
clúster. La puerta manda `/api/matches` a la API, quitándole el prefijo, y
todo lo demás al frontend:

```
navegador ──▶ Traefik :80 ──┬── /             ──▶ frontend   la página (nginx)
                            │
                            └── /api/matches  ──▶ api        como /matches
                                                   ├──▶ Redis        ¿está cacheada?
                                                   └──▶ PostgreSQL   solo si no lo está
```

En Compose, la puerta es el propio nginx del `frontend`, en
`http://localhost:8080`, con las mismas dos reglas (ver [Frontend](#frontend)).

La página pide los datos con una ruta relativa, `/api/matches`, así que la
página y la API comparten origen y el navegador no necesita CORS (ver
[Sin CORS](#sin-cors)).

`collector` arranca, descarga, guarda y termina. En el clúster lo lanza un
CronJob cada hora. En Compose se ejecuta una vez al hacer `up`, y después a
mano con `docker compose run --rm collector`. `db`, `redis`, `api` y
`frontend` se quedan en marcha.

Ningún endpoint de la API llama a Riot: sirve solo lo que ya está guardado,
así que consultar las estadísticas no gasta peticiones. Y cuando la
respuesta está en Redis, tampoco se consulta PostgreSQL.

### Qué hay hecho

- **`collector`** — dado un Riot ID: PUUID (ACCOUNT-V1), icono y nivel
  (SUMMONER-V4), una foto de la clasificatoria (LEAGUE-V4), identificadores
  de las últimas partidas de ranked solo (MATCH-V5), y de cada una su detalle y su
  timeline. Guarda la partida, los diez participantes y los eventos de
  compra y de habilidades, sin duplicar. Antes de descargar consulta
  cuáles ya están en la base y se las salta, así que solo pide a Riot lo
  que le falta. Con reintentos ante fallos de red y control del límite de
  peticiones.
- **`db`** — las tablas en PostgreSQL, volumen con nombre para
  que los datos sobrevivan a los reinicios y arranque ordenado con
  healthcheck.
- **`flyway`** — aplica las migraciones pendientes al arrancar y termina.
  Los servicios que usan la base esperan a que acabe.
- **`api`** — los endpoints con FastAPI, agregados calculados en SQL y
  documentación interactiva automática en `/docs`.
- **`redis`** — caché de respuestas de la API, con caducidad automática y
  opcional: si Redis no responde, la API consulta PostgreSQL y sigue
  funcionando.
- **`frontend`** — una página estática que pide los datos a la API desde el
  navegador, por la misma puerta por la que llega la página.
- **Tests** — pytest sobre todos los endpoints y la caché, contra un
  PostgreSQL y un Redis propios, con datos inventados.
- **CI** — GitHub Actions pasa Ruff, ejecuta los tests, revisa el chart de
  Helm y construye las imágenes en cada push, y marca cada commit en verde
  o en rojo. En `main` sube además las imágenes a GitHub Container Registry.
- **Kubernetes** — todo el proyecto en un clúster local con kind: la API y
  el frontend con dos réplicas cada uno, Redis, PostgreSQL y el `collector`,
  que un CronJob lanza cada hora. Se instala con un chart de Helm propio,
  las imágenes salen del CI, el esquema lo aplica un hook antes de cada
  despliegue, los datos de PostgreSQL viven en un disco que se conserva y el
  tráfico de fuera entra por Traefik con Gateway API.

### Qué falta

- La página definitiva con todos los datos de la API (en marcha)

El resto, y la deuda técnica, están en [MEJORAS.md](MEJORAS.md).

## Requisitos

- Docker
- kind, kubectl y Helm 4, para el clúster local de Kubernetes
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
```

El Riot ID va separado: si eres `TuNombre#EUW`, el nombre va en
`RIOT_GAME_NAME` y el tag en `RIOT_TAG_LINE`, sin almohadilla.

`MATCH_COUNT` es cuántas partidas recientes se le piden a Riot en cada
ejecución. Si falta, se usan 20. Como el `collector` no vuelve a pedir las
que ya tiene, subirlo solo cuesta peticiones la primera vez.

`TZ` es la zona horaria de los contenedores, y es la que sale en los logs.
Va en hora de Madrid y no en `UTC` para leer los logs sin convertir la hora.

`CACHE_TTL_SECONDS` es cuántos segundos vive cada respuesta cacheada. Es
el desfase máximo entre lo que hay en PostgreSQL y lo que devuelve la API.
Subirlo alivia a PostgreSQL a costa de servir datos más viejos.

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

Los cambios de esquema no necesitan `down -v`: se escriben como una
migración nueva y `flyway` la aplica al arrancar, sin tocar los datos.
Ver [Migraciones](#migraciones).

## Base de datos

Seis tablas y una vista:

- `summoners` — traduce cada PUUID a un Riot ID legible, con su icono de
  perfil y su nivel
- `matches` — fecha, duración, tipo de cola y parche de cada partida
- `participants` — los diez jugadores de cada partida: campeón, posición,
  KDA, resultado, oro, daño hecho y recibido, CS, visión, objetos finales,
  hechizos de invocador, equipo, nivel, runas y su rango de Solo/Duo
- `item_purchases` — cada compra de cada jugador, con su minuto
- `skill_levelups` — cada subida de habilidad, con su minuto
- `ranked_snapshots` — una foto de la clasificatoria solo/duo en cada vuelta
  del `collector`: liga, división, LP, victorias, derrotas y el corte del
  siguiente escalón. Se guardan todas para poder dibujar más adelante la
  evolución de los LP
- `participant_scores` — la vista con la nota y el sello de cada jugador
  (ver [La nota y los sellos](#la-nota-y-los-sellos))

Todos esos datos, salvo el rango, vienen en la misma respuesta de MATCH-V5,
así que guardarlos no cuesta ninguna petición extra a Riot.

El rango de cada jugador sale de LEAGUE-V4, con una petición por jugador.
Son nueve más por partida, porque el tuyo ya se pide para
`ranked_snapshots`. Dentro de una misma vuelta del `collector` se reutiliza
si el jugador sale en varias partidas. Es el rango del momento en que se
guarda la partida, porque Riot no da el que tenía al jugarla. Se pide con
su PUUID, pero solo se guarda el rango.

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

Una clave primaria crea su índice automáticamente. La anterior,
`(match_id, puuid)`, servía además para buscar por `puuid`; la nueva no,
porque esa columna ya no está. Por eso `V6` crea `idx_participants_puuid`
aparte.

### La nota y los sellos

Cada jugador de cada partida tiene una nota de 0 a 10, y el mejor de cada
equipo se lleva un sello: **MVP** en el equipo que gana y **BASTION** en el
que pierde. La idea es la de op.gg, pero op.gg no publica su fórmula, así que
esta es propia.

La nota sale de cuatro estadísticas. Cada una se divide por la mejor de los
diez jugadores de esa partida, así que queda entre 0 y 1 y una partida larga
no da notas más altas que una corta.

- KDA, `(kills + asistencias) / muertes`, contando 0 muertes como 1
- participación en asesinatos
- daño a campeones
- puntuación de visión, que cuenta la mitad

```
nota = 10 × (kda + participación + daño + 0,5 × visión) / 3,5
```

El 3,5 es la suma de los pesos, así que quien sea el mejor en las cuatro saca
un 10. La visión cuenta la mitad porque se puede inflar poniendo guardianes
sin que cueste nada. Con el mismo peso que las demás, un Blitzcrank 3/7/12
salía BASTION en una partida en la que deeplol lo ponía octavo de diez. El
daño recibido se descartó, porque recibir mucho no dice por sí solo que se
haya jugado bien.

Se calcula en la vista `participant_scores` (`V8`). Una vista es una consulta
guardada con nombre, que no guarda filas y se calcula cada vez que se lee,
así que siempre sale de lo que haya en `participants`. Se eligió una vista
normal y no una materializada para no tener que refrescarla después de cada
vuelta del `collector`.

Reglas de los sellos:

- Solo hay uno por equipo. Si dos notas empatan, gana el `participant_id` más
  bajo, para que el resultado no cambie de una consulta a otra.
- Sin nota no hay sello. Las partidas guardadas antes de tener a los diez
  jugadores o el daño tienen esas columnas a `NULL`, y su nota también.
- La nota se redondea a un decimal al final, después de elegir el sello.
  Redondeando antes, un 7,46 y un 7,44 empatarían en 7,4.

`/matches` devuelve el sello del invocador en cada partida, y
`/matches/{match_id}` la nota y el sello de los diez jugadores.

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

Solo vuelve a pedir las partidas de la lista que da Riot, que mide
`MATCH_COUNT` (20 por defecto). Para llegar más atrás se sube solo para esa
ejecución, sin tocar el `.env`:

```bash
docker compose run --rm -e MATCH_COUNT=70 collector python collector.py --refetch
```

Así también se bajan las partidas que nunca se guardaron. En Compose el
`collector` solo corre con `up`, y si entre dos vueltas se juegan más de
`MATCH_COUNT` partidas, las más antiguas de ese tramo se quedan sin bajar.

La lista de Riot da como mucho cien partidas por petición y el `collector`
no pide más, así que las anteriores no se pueden volver a pedir y una
columna añadida tarde se queda con `NULL` para siempre en esas.

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

## API

Servicio `api`, con FastAPI y uvicorn. En Compose escucha en
`http://localhost:8000`, publicado solo en `127.0.0.1`. En el clúster solo se
publica `/matches`, como `http://localhost/api/matches` (ver
[Entrada al clúster](#entrada-al-clúster)).

Endpoints:

| Endpoint | Para qué | Parámetros |
|---|---|---|
| `GET /health` | Dice que el proceso responde, sin consultar nada. Es la liveness probe en Kubernetes | |
| `GET /ready` | Hace un `SELECT 1` contra PostgreSQL y devuelve 503 si no responde. Es la readiness probe | |
| `GET /summoners` | Los invocadores seguidos, con su icono de perfil y su nivel | |
| `GET /matches` | El historial de 10 en 10, de la partida más nueva a la más antigua, con el sello [MVP o BASTION](#la-nota-y-los-sellos). Viene como `{"matches": [...], "has_more": true}`, y `has_more` dice si quedan más | `patch`, `champion`, `offset` |
| `GET /matches/{match_id}` | El detalle de una partida: tus estadísticas, objetos, hechizos, compras con su minuto y los diez jugadores con su nota, su marcador, su nivel, sus runas y su rango. 404 si no existe | |
| `GET /patches` | Los parches que tienen partidas y cuántas hay en cada uno, del más reciente al más antiguo | |
| `GET /summary` | Partidas, victorias, derrotas y winrate de la temporada o de un parche | `patch` |
| `GET /rank` | La última foto de la clasificatoria solo/duo: liga, división, LP, balance de la temporada y corte del siguiente escalón. `null` si no hay ninguna | |
| `GET /rank/history` | La última foto de cada día de los últimos 30, para la gráfica de LP. `ladder_lp` son los LP contados desde Hierro IV, para que subir de división no parezca una bajada | |
| `GET /champions` | Estadísticas por campeón de la temporada o de un parche, del más jugado al menos | `patch` |

Los parámetros son opcionales y se pueden combinar, por ejemplo
`/matches?patch=26.17&champion=Ahri&offset=10`:

- `patch` es el parche como lo ve el jugador (`26.17`). Sin él, `/summary` y
  `/champions` usan la temporada actual y `/matches` todas las partidas.
- `champion` es la clave interna de Riot (`Kaisa`, `MonkeyKing`) y distingue
  mayúsculas.
- `offset` es cuántas partidas saltarse: `0` da las 10 primeras y `10` las
  siguientes. Un número negativo devuelve 422.

Riot no da la temporada de forma fiable, así que se deduce del primer número
de la versión interna (`16` en 2026). La temporada actual es la de la partida
más reciente.

`/summary` y `/rank` dan victorias y derrotas por caminos distintos.
`/summary` las cuenta en las partidas guardadas, que solo llegan hasta donde
empezó a recoger el collector. `/rank` las copia de Riot, que tiene la
temporada entera, así que el balance de la temporada sale de `/rank`.

Todos los endpoints de datos filtran por `puuid IS NOT NULL`. `participants`
guarda a los diez jugadores de cada partida y solo los invocadores seguidos
tienen PUUID, así que sin ese filtro los agregados incluirían a rivales y
compañeros. Cuando haya varios invocadores seguidos habrá que añadir un
parámetro para elegir de cuál.

Al levantar `api`, Compose arranca antes `db`, `flyway` y `redis`: espera
al healthcheck de los dos primeros y a que `flyway` termine bien.

Los endpoints de datos se cachean en Redis con estas claves:

```
GET /summoners            →  summoners:all
GET /matches              →  matches:<parche o all>:<campeón o all>:<offset>
GET /matches/{match_id}   →  match:<match_id>
GET /patches              →  patches:all
GET /summary              →  summary:<parche o season>
GET /rank                 →  rank:latest
GET /rank/history         →  rank:history
GET /champions            →  champions:<parche o season>
```

`/health` y `/ready` no se cachean. Las respuestas vacías también se guardan.
Una partida que no existe queda en Redis como `null`, y la API responde 404
sin volver a consultar PostgreSQL.

Además de Redis, `/matches/{match_id}` lleva `Cache-Control: max-age=3600`,
así que el navegador reutiliza el detalle de una partida durante una hora.
El 404 no lo lleva, porque la partida puede llegar en la siguiente vuelta
del `collector`.

FastAPI genera la documentación sola a partir de las rutas registradas:

- `http://localhost:8000/docs` — documentación navegable
- `http://localhost:8000/openapi.json` — el esquema en crudo

Comprobación rápida:

```bash
curl http://localhost:8000/health
curl -s "http://localhost:8000/matches?patch=26.21&champion=Yunara" | python3 -m json.tool
curl -s http://localhost:8000/rank | python3 -m json.tool
```

Las comillas de las URL con `&` hacen falta porque, sin ellas, la shell corta
la orden en el `&` y manda el `curl` a segundo plano.

`next_cutoff_lp`, en `/rank`, son los LP que hacen falta para subir desde Master
o Grandmaster. Riot lo recalcula cada día, así que cambia aunque tú no juegues.

Cómo es cada respuesta se ve en `http://localhost:8000/docs`. En cada endpoint,
*Try it out* y *Execute* llaman a la API de verdad y enseñan el JSON que
devuelve.

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

En el clúster las aplica el Job `migrations`, un hook de Helm que corre
antes de cada despliegue, con una imagen de Flyway que lleva los `.sql`
dentro (ver [Desplegar una versión nueva](#desplegar-una-versión-nueva)).

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

Se usó al introducir Flyway en el proyecto, sobre la base que ya tenía
partidas.

## Copia de seguridad

Desde Compose:

```bash
mkdir -p backups
docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > backups/project0-$(date +%F).dump
```

Desde el clúster, igual pero dentro de `postgres-0`:

```bash
mkdir -p backups
kubectl exec -n project0 postgres-0 -- sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > backups/project0-$(date +%F).dump
```

Va sin `-t` en `kubectl exec`, como con el `-T` de Compose, porque una
terminal estropearía la salida binaria de `pg_dump`.

Para ver qué tablas trae una copia sin restaurarla:

```bash
kubectl exec -i -n project0 postgres-0 -- pg_restore --list < backups/<fichero>.dump | grep 'TABLE DATA'
```

Para restaurarla en una base vacía de Compose:

```bash
docker compose exec -T db sh -c 'pg_restore -U "$POSTGRES_USER" -d <base>' < backups/<fichero>.dump
```

Para restaurarla en el clúster, sustituyendo lo que haya en `postgres-0`, y
aplicar después las migraciones escritas desde la copia:

```bash
kubectl exec -i -n project0 postgres-0 -- sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --single-transaction' < backups/<fichero>.dump
helm upgrade project0 charts/project0 -n project0 --wait --timeout 5m
```

El `helm upgrade` no cambia nada de la aplicación, pero lanza el hook de
las migraciones.

`--clean --if-exists` borra cada objeto de la copia antes de crearlo, y
`--single-transaction` hace que, si algo falla, la base se quede como
estaba.

La copia va en formato custom de `pg_dump` y la carpeta `backups/` está
fuera de Git. Se hace a mano, y la copia automática está en
[MEJORAS.md](MEJORAS.md).

## Frontend

Una página en `frontend/public/`, servida por nginx, que pide los datos
a la API y los pinta. Todo lo que hay en esa carpeta es público, y lo que no
está en ella no se sirve. En Compose se abre en `http://localhost:8080`, y en el
clúster en `http://localhost` (ver [Kubernetes](#kubernetes)).

En Compose, nginx hace también de puerta de entrada, como Traefik en el
clúster. Su configuración está en `frontend/nginx-compose.conf`: pasa todo
lo que empieza por `/api/` a la API quitándole el prefijo (`/api/rank` llega
como `/rank`) y sirve lo demás desde el disco. Por eso levantar el
`frontend` levanta también la API, y las respuestas de la API llegan con
`Server: nginx`.

Las rutas internas de la API (`/health`, `/ready`, `/docs`, `/redoc` y
`/openapi.json`) no se publican, y por la puerta de entrada devuelven 404.
Desde el propio ordenador siguen en `http://localhost:8000`.

Solo se monta `frontend/public/`, como bind mount de solo lectura, así que
editar la página y recargar el navegador basta: no hay que reconstruir ni
reiniciar nada. Si el cambio no se ve, suele ser la caché
del navegador (`Cmd + Shift + R`).

### Emblemas de rango

Los emblemas de `frontend/public/emblems/` son los oficiales de Riot, de
`ranked-emblems-latest.zip`, en la sección *Icons and Emblems* de la
documentación de League of Legends del portal de desarrolladores. Data
Dragon no los tiene. nginx los sirve en `/emblems/`, montados en Compose y
copiados dentro de la imagen en el clúster.

Vienen a 1000 × 1000 píxeles y unos 500 KB cada uno, así que se reducen a
256 y se renombran como el `tier` de `/rank` en minúsculas (`master.png`).
Para rehacerlos si Riot los cambia:

```bash
unzip -j ranked-emblems-latest.zip "Ranked Emblems Latest/Rank=*" -d /tmp/emblems
for f in /tmp/emblems/Rank=*.png; do
  name=$(basename "$f" .png | sed 's/^Rank=//' | tr '[:upper:]' '[:lower:]')
  sips -Z 256 "$f" --out "frontend/public/emblems/$name.png" >/dev/null
done
```

`sips` viene con macOS. En Linux, ImageMagick hace lo mismo con
`magick "$f" -resize 256x256 "frontend/public/emblems/$name.png"`.

### Sin CORS

La página pide `/api/matches` con una ruta relativa, así que la petición va
al mismo sitio del que salió la página: mismo protocolo, host y puerto.
Para el navegador, la página y la API son el mismo origen, y puede leer sus
respuestas sin pedir permiso.

Antes, en Compose, la página estaba en el 8080 y la API en el 8000, que son
orígenes distintos, y la API autorizaba a la página con `CORSMiddleware` y
la variable `CORS_ORIGINS`. Al pasar las dos por la misma puerta se
quitaron. Si algún día una página de otro origen necesita leer la API, habrá
que volver a añadirlos.

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
docker compose -f docker-compose.test.yml up -d --wait db-test redis-test
docker compose -f docker-compose.test.yml run --rm flyway-test
source .venv/bin/activate
pytest
```

Los dos primeros comandos son los mismos que usa el CI. Un `up -d` a secas
vuelve antes de que `flyway-test` acabe de crear las tablas, y si `pytest`
llega antes falla con `relation "summoners" does not exist`. `--wait` espera
a que la base y Redis estén sanos y `run` espera a que Flyway termine.

Los contenedores se quedan levantados entre ejecuciones, así que basta con
lanzar `pytest`. El `run` de `flyway-test` hay que repetirlo después de añadir
una migración, porque si no los tests corren contra el esquema anterior. Sin
los contenedores, `/health` pasa igual y el resto falla con un error de
conexión al puerto 5433 o al 6380. Para tirarlos al acabar:

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

Cada push, a cualquier rama, ejecuta el pipeline de GitHub Actions
definido en `.github/workflows/ci.yml`. Así un cambio se puede probar en una
rama antes de que llegue a `main`.

El workflow tiene cuatro jobs, `lint`, `tests`, `chart-lint` y `build`. Los
tres primeros arrancan a la vez, cada uno en su propia máquina Ubuntu que
GitHub borra al acabar. Que falle uno no para a los otros, así que un fallo
de formato no esconde si los tests pasan. `build` espera a que pasen los
tres.

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

### chart-lint

Revisa el chart de Helm de la aplicación:

```bash
helm lint --strict charts/project0
```

Comprueba que `Chart.yaml` está completo, que los templates se rellenan
con los values sin errores y que el resultado es YAML válido. Con `--strict`
fallan también los avisos, no solo los errores. No comprueba que el chart
funcione en un clúster, solo que está bien escrito.

Helm lo instala `azure/setup-helm`, fijado a la misma versión que se usa en
local, para que `helm lint` dé el mismo resultado en los dos sitios.

### build

Construye las tres imágenes del proyecto con las acciones oficiales de
Docker (`docker/setup-buildx-action` y `docker/build-push-action`). Es un
`matrix`: el job se escribe una vez y GitHub lanza una copia por imagen, a
la vez:

```
build (api)          Dockerfile              ghcr.io/liamxcx/project0
build (migrations)   migrations/Dockerfile   ghcr.io/liamxcx/project0-migrations
build (frontend)     frontend/Dockerfile     ghcr.io/liamxcx/project0-frontend
```

Hace falta porque los tests ejecutan el código directamente y nunca usan el
`Dockerfile`, así que un `COPY` de un fichero que no existe o un
`pip install` que falla dentro de la imagen no saldría en ningún otro
sitio.

En `main` las construye para amd64 y arm64 y las sube a GitHub Container
Registry, con el SHA corto del commit como tag. Las tres llevan el mismo
tag, así que se sabe qué migraciones y qué página van con qué código. En el resto de
ramas solo las construye para amd64 y no las sube, así que el aviso
`No output specified with docker-container driver` del log es esperado.
Las capas se guardan en la caché de Actions para no reconstruir lo que no
ha cambiado.

`build` solo arranca si pasan `lint`, `tests` y `chart-lint`, para no subir
nunca una imagen si el código falla o si el chart que la va a desplegar
tiene errores. Si falla una de las copias, GitHub cancela las demás.

### El sistema del runner

Todos los jobs usan `ubuntu-latest`, que GitHub mueve a la siguiente
versión LTS cuando sale. Se deja así porque del sistema solo se usa Docker.
Python y Helm los instalan `setup-python` y `setup-helm` en la versión
indicada, y lo demás va en contenedores con la imagen fijada.

## Kubernetes

Clúster local con kind, definido en `kind-config.yaml`: un control plane y
dos workers.

```bash
kind create cluster --config kind-config.yaml   # crearlo
kubectl get nodes                               # los tres nodos en Ready
kind delete cluster --name project0             # borrarlo
```

El primer worker publica el 80 y el 443 en `127.0.0.1` para Traefik (ver
[Entrada al clúster](#entrada-al-clúster)).
Los puertos solo se fijan al crear el clúster, así que cambiar
`kind-config.yaml` obliga a borrarlo y crearlo otra vez, y se pierde lo que
haya dentro.

La aplicación se instala con un chart de Helm propio, en `charts/project0`,
como la release `project0` del namespace `project0`. Lo que va fuera del
chart, como el namespace, la StorageClass y el Gateway, está en `platform/`.

### Instalar desde cero

En un clúster recién creado, en este orden:

```bash
# 1. Los tipos de Gateway API, que no vienen con Kubernetes
kubectl apply -f https://github.com/kubernetes-sigs/gateway-api/releases/download/v1.6.3/standard-install.yaml

# 2. Traefik, la entrada al clúster
helm repo add traefik https://traefik.github.io/charts
helm install traefik traefik/traefik --version 42.1.3 \
  --namespace traefik --create-namespace \
  --values platform/helm/traefik-values.yaml

# 3. El namespace de la aplicación, la StorageClass y el Gateway
kubectl apply -f platform/

# 4. Los Secrets, que no están en el repo
read -rs GHCR_TOKEN
kubectl create secret docker-registry ghcr-pull -n project0 \
  --docker-server=ghcr.io --docker-username=<usuario de GitHub> \
  --docker-password="$GHCR_TOKEN"

kubectl create secret generic db-credentials -n project0 \
  --from-literal=POSTGRES_PASSWORD="$(grep '^POSTGRES_PASSWORD=' .env | cut -d= -f2-)"

kubectl create secret generic riot-credentials -n project0 \
  --from-literal=RIOT_API_KEY="$(grep '^RIOT_API_KEY=' .env | cut -d= -f2-)"

# 5. La aplicación
helm install project0 charts/project0 -n project0 --wait --timeout 5m
```

El token de GHCR es un token classic de GitHub con solo el permiso
`read:packages`. Los otros dos valores salen del `.env`.

El namespace y los Secrets van fuera del chart. Helm guarda la release
dentro del namespace, y `helm uninstall` lo borraría con todo lo que tiene
dentro. Y si los Secrets fueran templates del chart, sus valores
acabarían en el historial de cada revisión.

En un clúster nuevo PostgreSQL arranca vacío. Al instalar, las migraciones
crean el esquema, y los datos se traen restaurando una copia (ver
[Copia de seguridad](#copia-de-seguridad)).

Para llamar a las rutas de la API que no se publican, como `/ready` (el 8000
lo ocupa Compose):

```bash
kubectl get pods -n project0                          # api y frontend (dos de cada), redis y postgres-0 en 1/1
kubectl port-forward -n project0 service/api 8001:80  # y en otra terminal:
curl localhost:8001/ready
```

### El chart

`charts/project0` tiene cuatro partes:

- `Chart.yaml` — el nombre y dos versiones. `version` es la del chart y se
  sube a mano cuando cambian los templates o lo que se puede configurar.
  `appVersion` es el tag de las imágenes que despliega.
- `values.yaml` — lo que puede cambiar de un clúster a otro o con el
  tiempo, como el tag, las réplicas, los recursos, el horario del
  `collector`, la configuración de la API, el disco de PostgreSQL y el
  Gateway del que cuelga la ruta.
- `templates/` — un template por objeto de la aplicación.
- `templates/_helpers.tpl` — los labels comunes y la regla del tag, que
  usan varios templates.

En el clúster, la configuración que no es secreta no sale del `.env`, sino
de los ConfigMaps del chart, que se rellenan con `values.yaml`. El template
de los pods de la API lleva una suma de cada ConfigMap que lee, así que si
un `helm upgrade` cambia uno de esos valores, cambia la suma y Kubernetes
recrea los pods con el valor nuevo. El `collector` no lo necesita, porque
cada ejecución es un pod nuevo.

Las migraciones las aplica un hook de Helm, un Job que no se instala con lo
demás sino en el momento que marca su anotación. En la primera instalación
corre después de crearlo todo, porque necesita PostgreSQL, y en cada
upgrade corre antes de tocar la API. El Job se queda hasta el siguiente
upgrade, con sus logs.

El disco de PostgreSQL (`postgres.storage`) solo se elige al crear el
StatefulSet. Kubernetes no deja cambiar `volumeClaimTemplates` después, así
que cambiarlo en una instalación que ya existe hace fallar el upgrade.

Para revisar el chart y ver qué cambiaría antes de desplegar:

```bash
helm lint --strict charts/project0                                                 # lo mismo que hace el CI
helm template project0 charts/project0 -n project0 --no-hooks | kubectl diff -f -  # la diferencia con el clúster
```

El diff va sin los hooks porque Kubernetes no deja cambiar el pod de un
Job ya creado. Con una imagen nueva, el Job de las migraciones daría error
en vez de enseñar la diferencia, y Helm lo recrea en cada upgrade de todos
modos.

### Desplegar una versión nueva

Cada push a `main` sube las tres imágenes con el SHA corto del commit. Para
desplegarlas, se pone ese tag en `appVersion`, en
`charts/project0/Chart.yaml`, y:

```bash
helm upgrade project0 charts/project0 -n project0 --wait --timeout 5m
helm history project0 -n project0                     # la revisión nueva, en deployed
```

Helm lanza primero las migraciones y espera a que acaben, porque el código
nuevo puede necesitar una columna nueva. Si fallan, el upgrade se para, la
versión anterior sigue atendiendo y el motivo está en
`kubectl logs job/migrations -n project0`. Después Helm aplica lo demás, y
Kubernetes sustituye los pods de la API y del frontend de uno en uno. Con
`--wait`, Helm no da el despliegue por bueno hasta que los nuevos están
listos.

El CronJob usa la imagen nueva desde su siguiente ejecución.

Un cambio en `values.yaml` o en un template se despliega igual. Si
cambian los templates o lo que se puede configurar, se sube también
`version` en `Chart.yaml`.

El commit se hace después de comprobar que funciona, para que lo que hay en
`main` coincida siempre con lo desplegado.

Los cambios se hacen siempre en el chart. Aplicar un manifiesto suelto con
`kubectl apply` sobre la aplicación haría a `kubectl` dueño de esos campos,
y el siguiente `helm upgrade` fallaría por conflicto.

### Volver atrás

Si el despliegue no termina, los pods viejos siguen atendiendo hasta que el
nuevo pasa la readiness. Para ver qué falla:

```bash
kubectl get pods -n project0
kubectl describe pod <pod nuevo> -n project0          # los eventos, al final
```

Para volver a una revisión anterior:

```bash
helm history project0 -n project0
helm rollback project0 <revisión> -n project0 --wait --timeout 5m
```

El rollback crea una revisión nueva con lo que tenía la elegida. No vuelve a
lanzar las migraciones ni deshace las que ya se aplicaron, porque solo van
hacia delante. Tampoco toca el repo, así que después hay que dejar los
ficheros como el clúster, por ejemplo con `git restore`, o el siguiente
`upgrade` volvería a traer lo que falló.

Un upgrade que falla puede dejar aplicada una parte de los objetos. Si un
ConfigMap ya cambió en el upgrade fallido, el que lo arregla no cambia la
suma y no recrea los pods, así que conviene comprobar que tienen la
configuración nueva, por ejemplo con
`kubectl exec -n project0 deploy/api -- printenv CACHE_TTL_SECONDS`.

### De manifiestos sueltos a Helm

Antes del chart, la aplicación se desplegaba con manifiestos sueltos y
`kubectl apply`. Se pasó a Helm sin caída, adoptando los objetos que ya
corrían en vez de recrearlos. Para eso se les puso el label
`app.kubernetes.io/managed-by: Helm` y las dos anotaciones
`meta.helm.sh/…` con las que Helm reconoce lo suyo.

Helm 4 aplica con server-side apply, en el que el apiserver apunta qué
herramienta es dueña de cada campo (los `managedFields`). Los campos que
había escrito `kubectl` seguían siendo también suyos y bloqueaban los
cambios, así que se quitó a `kubectl` de los `managedFields` de cada objeto
con `kubectl patch`.

### PostgreSQL

Corre en un StatefulSet con una réplica, y no en un Deployment, porque
necesita un disco propio que vuelva con él. El pod se llama siempre
`postgres-0` y su disco es el PVC `datos-postgres-0`, que el StatefulSet
crea a partir de `volumeClaimTemplates`. Si se borra el pod, vuelve con el
mismo nombre y el mismo disco, aunque con otra IP.

El disco usa la StorageClass `standard-retain`, definida en
`platform/storageclass.yaml`. Es igual que la `standard` de kind, pero con
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
kubectl get cronjob collector -n project0     # horario y última ejecución
kubectl get jobs -n project0                  # una por hora, Complete o Failed
kubectl logs -n project0 -l app.kubernetes.io/name=collector --prefix --tail=-1
kubectl create job collector-manual -n project0 --from=cronjob/collector   # ejecutarlo ya
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

Cada ejecución mira las últimas `MATCH_COUNT` partidas (20, en
`collector.matchCount` de `values.yaml`). Si se juegan más con el clúster
parado, las más antiguas se recuperan lanzándolo a mano con un
`MATCH_COUNT` más alto.

### Frontend

En el clúster la página va dentro de su propia imagen, construida con
`frontend/Dockerfile`: nginx sin root, que escucha en el 8080, con el
`index.html` copiado. Así que un cambio en la página necesita una imagen
nueva, como el resto del código. La sirven dos réplicas detrás del Service
`frontend`, y desde fuera se llega por Traefik (ver
[Entrada al clúster](#entrada-al-clúster)).

### Entrada al clúster

El tráfico de fuera entra por Traefik, que lee los `Gateway` y `HTTPRoute`
de Gateway API. Su configuración está en `platform/`, aparte de la de la
aplicación, y se instala una vez por clúster (ver
[Instalar desde cero](#instalar-desde-cero)).

En kind, Traefik escucha en el 80 de `project0-worker`, que kind une con el
80 de la máquina. En un clúster real iría detrás de un Service
`LoadBalancer`.

Para cambiar un value de Traefik, se edita `traefik-values.yaml` y se
ejecuta el comando de la instalación con `upgrade` en vez de `install`,
siempre con `--values`.

Las reglas de project0 van en la HTTPRoute `project0`, un template más del
chart, colgada del Gateway `public` (`gateway` en `values.yaml`):

```
/api/matches   →  Service api, como /matches
/              →  Service frontend
```

La API tiene sus rutas sin prefijo, así que la HTTPRoute lo quita con un
filtro `URLRewrite`. Solo se publica la ruta que usa la página. `/health`,
`/ready`, `/docs` y el resto de la API se quedan dentro del clúster.

```bash
helm list -n traefik                              # la release y su revisión
kubectl get gateway -n traefik                    # public, con PROGRAMMED True
kubectl describe httproute project0 -n project0   # Accepted y ResolvedRefs en True
curl -i http://localhost/api/matches              # la API, a través de Traefik
```

## Estructura

```
test_api.py             los tests de la API                   → se lanzan con pytest
conftest.py             prepara la base y los datos de test
collector.py            baja partidas de Riot y las guarda    → servicio collector
api.py                  sirve lo guardado por HTTP            → servicio api
config.py               la configuración, en un solo sitio    → lo importan los dos
migrations/             el esquema, versionado paso a paso    → servicio flyway y Job migrations
migrations/Dockerfile   la imagen de migraciones para el clúster
frontend/public/        la página, sus emblemas y su fuente   → servicio frontend
frontend/Dockerfile     la imagen del frontend para el clúster
frontend/nginx-compose.conf la puerta de entrada en Compose   → servicio frontend
frontend/borrador/      notas para trabajar el diseño aparte
Dockerfile              la imagen de collector y api
docker-compose.yml      los seis servicios, el volumen y los healthchecks
docker-compose.test.yml la base y el Redis de test, aparte
kind-config.yaml        el clúster local de Kubernetes        → kind create cluster
charts/project0/        el chart de Helm de la aplicación     → helm install / upgrade
platform/               namespace, StorageClass y Gateway     → kubectl apply -f platform/
platform/helm/          los values del chart de Traefik       → helm install / upgrade
requirements.txt        dependencias de Python, con versiones fijadas
requirements-dev.txt    pytest, Ruff y compañía, fuera de la imagen
.github/workflows/      el pipeline de GitHub Actions         → se ejecuta en cada push
MEJORAS.md              lo que falta por hacer y la deuda técnica
backups/                copias de la base con pg_dump (fuera del repo)
.env                    los valores reales (fuera del repo y de la imagen)
.env.example            las mismas claves, sin valores
```

## Notas

Las rutas usan hosts distintos según la API. ACCOUNT-V1 y MATCH-V5 van por
región grande, `europe.api.riotgames.com`. LEAGUE-V4 y SUMMONER-V4, que dan
el rango y el icono, van por plataforma, `euw1.api.riotgames.com`.

`api` arranca uvicorn con `--host 0.0.0.0`. Por defecto uvicorn escucha en
`127.0.0.1`, que dentro del contenedor significa solo el propio contenedor:
el puerto quedaría publicado sin nadie escuchando detrás.

`collector` y `api` comparten Dockerfile y se diferencian por el `command`
del compose: `collector` usa el `CMD` de la imagen (`python collector.py`)
y `api` lo sustituye por uvicorn.

El servicio `db` tiene un healthcheck con `pg_isready`, y `flyway` usa
`depends_on` con `condition: service_healthy`. Sin eso, `depends_on` solo
esperaría a que el contenedor arrancase, no a que PostgreSQL aceptase
conexiones, y las migraciones podrían fallar al conectar. `collector` y `api`
esperan a su vez a que `flyway` termine bien.

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
