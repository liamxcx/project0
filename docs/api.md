# API

Servicio `api`, con FastAPI y uvicorn. Sirve lo que ha guardado el collector
y no llama nunca a Riot, así que consultar las estadísticas no gasta
peticiones.

En Compose escucha en `http://localhost:8000`, publicado solo en
`127.0.0.1`. En el clúster se publica bajo `http://localhost/api/`, todo
menos las rutas internas (ver
[kubernetes.md](kubernetes.md#entrada-al-clúster)).

## Endpoints

| Endpoint | Para qué | Parámetros |
|---|---|---|
| `GET /health` | Dice que el proceso responde, sin consultar nada. Es la liveness probe en Kubernetes | |
| `GET /ready` | Hace un `SELECT 1` contra PostgreSQL y devuelve 503 si no responde. Es la readiness probe | |
| `GET /summoners` | Los invocadores seguidos, con su icono de perfil y su nivel | |
| `GET /matches` | El historial de 10 en 10, de la partida más nueva a la más antigua, con el sello [MVP o BASTION](base-de-datos.md#la-nota-y-los-sellos). Viene como `{"matches": [...], "has_more": true}`, y `has_more` dice si quedan más | `patch`, `champion`, `offset` |
| `GET /matches/{match_id}` | El detalle de una partida: las estadísticas del invocador seguido y los diez jugadores con su nota, su marcador, su nivel, sus runas, su rango, sus compras con su minuto y su orden de habilidades. 404 si no existe | |
| `GET /patches` | Los parches que tienen partidas y cuántas hay en cada uno, del más reciente al más antiguo | |
| `GET /summary` | Partidas, victorias, derrotas y winrate de la temporada o de un parche | `patch` |
| `GET /rank` | El último snapshot de la clasificatoria solo/duo: liga, división, LP, balance de la temporada y corte del siguiente escalón. `null` si no hay ninguno | |
| `GET /rank/history` | El último snapshot de cada día de los últimos 30, para la gráfica de LP. `ladder_lp` son los LP contados desde Hierro IV, para que subir de división no parezca una bajada | |
| `GET /champions` | Estadísticas por campeón de la temporada o de un parche, del más jugado al menos. `kda_ratio` sale de las sumas y no de las medias redondeadas, y es `null` si no hay ninguna muerte | `patch` |

Los parámetros son opcionales y se pueden combinar, por ejemplo
`/matches?patch=26.17&champion=Ahri&offset=10`:

- `patch` es el parche como lo ve el jugador (`26.17`). Sin él, `/summary` y
  `/champions` usan la temporada actual y `/matches` todas las partidas.
- `champion` es la clave interna de Riot (`Kaisa`, `MonkeyKing`) y distingue
  mayúsculas.
- `offset` es cuántas partidas saltarse: `0` da las 10 primeras y `10` las
  siguientes. Un número negativo devuelve 422.

`next_cutoff_lp`, en `/rank`, son los LP que hacen falta para subir desde
Master o Grandmaster. Riot lo recalcula cada día, así que cambia aunque el
invocador no juegue.

Todos los endpoints de datos filtran por `puuid IS NOT NULL`. `participants`
guarda a los diez jugadores de cada partida y solo los invocadores seguidos
tienen PUUID, así que sin ese filtro los agregados incluirían a rivales y
compañeros. Cuando haya varios invocadores seguidos habrá que añadir un
parámetro para elegir de cuál.

## Parche y temporada

`game_version` es la numeración interna de Riot, la que da su API. No
coincide con la que ve el jugador en el cliente, porque la pública va diez
por delante en el primer número (interna `16.17` = pública `26.17`). Cada
serie interna corresponde a un año natural. La API hace la conversión al
consultar, y en la base solo se guarda el valor original.

Riot no da la temporada de forma fiable, así que se deduce del primer número
de la versión interna (`16` en 2026). La temporada actual es la de la partida
más reciente.

`/summary` y `/rank` dan victorias y derrotas por caminos distintos.
`/summary` las cuenta en las partidas guardadas, que solo llegan hasta donde
empezó a recoger el collector. `/rank` las copia de Riot, que tiene la
temporada entera, así que el balance de la temporada sale de `/rank`.

## Caché en Redis

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

Cada clave lleva delante la versión de la API, que es el tag de su imagen,
como `913b445:match:EUW1_…`, y `dev:` en Compose. En un rolling update conviven
pods de las dos versiones, y así ninguno lee lo que guardó el otro con otro
formato. Las claves de la versión vieja caducan solas con el TTL.

Redis es opcional. Las llamadas a la caché van envueltas en `cache_get` y
`cache_set`, que capturan cualquier error y lo tratan como "no hay nada
cacheado", así que la API responde igual, más lenta, y deja un aviso en los
logs. El cliente lleva además `socket_timeout=1`, para que un Redis que
acepta la conexión pero no contesta no deje la petición esperando. Un test
comprueba que la API responde con Redis caído (ver
[tests-y-ci.md](tests-y-ci.md)).

## ETag y gzip

Además de Redis, `/matches/{match_id}` lleva una ETag, una huella del JSON, y
`Cache-Control: no-cache`. El navegador guarda el detalle, pero pregunta
antes de usarlo, y si no ha cambiado la API responde 304 sin cuerpo. Así
nunca usa una copia vieja después de un despliegue que cambie la respuesta.
El 404 no lleva nada de esto, porque la partida puede llegar en la siguiente
ejecución del collector.

Las respuestas desde 500 bytes salen comprimidas con gzip cuando el cliente
lo pide, con el `GZipMiddleware` de FastAPI. Va en la API y no en nginx ni en
Traefik para que valga igual en Compose y en el clúster. El detalle de una
partida pasa de unos 13 kB a unos 2 kB.

## Probarla

FastAPI genera la documentación sola a partir de las rutas registradas, en
`http://localhost:8000/docs`, y el esquema en crudo en
`http://localhost:8000/openapi.json`. En cada endpoint de `/docs`,
*Try it out* y *Execute* llaman a la API de verdad y enseñan el JSON que
devuelve.

Desde la terminal:

```bash
curl http://localhost:8000/health
curl -s "http://localhost:8000/matches?patch=26.21&champion=Yunara" | python3 -m json.tool
curl -s http://localhost:8000/rank | python3 -m json.tool
```
