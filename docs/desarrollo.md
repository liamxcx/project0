# Desarrollo con Compose

Compose es el entorno de desarrollo. Levanta en la máquina los servicios de
la aplicación, con la página y la configuración de nginx montadas
desde el disco, así que un cambio en la página se ve recargando el navegador.
El clúster está en [kubernetes.md](kubernetes.md).

## Requisitos

- Docker
- Una clave de la API de Riot: https://developer.riotgames.com.
  La Development Key caduca cada 24 horas. Una personal key, que se pide
  registrando el proyecto en el portal, no caduca.
- Python 3.14, para lanzar los tests en local (ver
  [tests-y-ci.md](tests-y-ci.md)). La misma versión que la imagen:

```bash
python3.14 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
```

## Configuración

Copiar `.env.example` a `.env` y rellenar los valores.

El Riot ID va separado. Si eres `TuNombre#EUW`, el nombre va en
`RIOT_GAME_NAME` y el tag en `RIOT_TAG_LINE`, sin almohadilla.

`MATCH_COUNT` es cuántas partidas recientes se le piden a Riot en cada
ejecución. Si falta, se usan 20. Como el collector no vuelve a pedir las
que ya tiene, subirlo solo cuesta peticiones la primera vez.

`TZ` es la zona horaria de los contenedores, y es la que sale en los logs.
Va en hora de Madrid y no en `UTC` para leer los logs sin convertir la hora.

`CACHE_TTL_SECONDS` es cuántos segundos vive cada respuesta cacheada. Es
el desfase máximo entre lo que hay en PostgreSQL y lo que devuelve la API.
Subirlo alivia a PostgreSQL a costa de servir datos más viejos.

`DB_HOST` es `db` dentro de Compose. En el clúster es `postgres` y lo pone
el ConfigMap `project0-config`. Para ejecutar el collector o la API fuera de
Docker hay que ponerlo a `localhost`.

`DB_PORT` no va en el `.env` y vale 5432 si falta. Solo lo cambian los
tests, que usan su propia base en el 5433.

Las variables sin valor por defecto pasan por `required_env()`, que corta la
ejecución con un mensaje claro si faltan. Sin eso, una variable ausente se
cuela como el texto `None` dentro de la cadena de conexión y el fallo
aparece más tarde, al conectar, diciendo que la contraseña es incorrecta
cuando lo que pasa es que no hay ninguna.

## Ejecución

```bash
docker compose up
```

Levanta los seis servicios. El esquema lo aplica `flyway` antes de que
arranquen `collector` y `api`, y la API espera además a que Redis esté sano.

Los servicios no se comportan igual:

- `db`, `redis`, `api` y `frontend` son procesos largos, que se quedan
  corriendo hasta que se paran.
- `collector` y `flyway` terminan cuando acaban su trabajo. En
  `docker compose ps` aparecen como `Exited (0)`, que no es un error.

El collector se ejecuta una vez al hacer `up`, y después a mano:

```bash
docker compose run --rm collector
```

La página no enseña el botón de actualizar, porque funciona creando un Job
de Kubernetes y en Compose no hay ninguno. Para actualizar se usa este
comando.

Qué comando usar según lo que hayas cambiado:

- Con un cambio en `docker-compose.yml`, en el `.env` o una migración nueva,
  basta con `docker compose up`.
- Con un cambio en el código o en `requirements.txt`, hace falta
  `docker compose up --build`.

El `--build` hace falta porque los ficheros `.py` y `requirements.txt` se
copian dentro de la imagen. El `.env` y las migraciones se leen al arrancar,
así que esos no lo necesitan.

Va sin nombrar servicio. `collector` y `api` comparten el `Dockerfile`, pero
Compose construye una imagen por servicio, así que
`docker compose up --build api` reconstruye solo esa y deja la otra con el
código anterior, sin dar ningún error. Nombrar un servicio vale para
levantarlo suelto, no para reconstruir.

Al recrear la API, Compose reinicia también el `frontend`, porque su nginx
necesita la IP nueva de la API (ver [frontend.md](frontend.md)).

Los cambios de esquema no necesitan `down -v`. Se escriben como una
migración nueva y `flyway` la aplica al arrancar, sin tocar los datos (ver
[base-de-datos.md](base-de-datos.md#migraciones)).

`api` arranca uvicorn con `--host 0.0.0.0`. Por defecto uvicorn escucha en
`127.0.0.1`, que dentro del contenedor significa solo el propio contenedor,
y el puerto quedaría publicado sin nadie escuchando detrás.

## Logs

Todo se registra con `logging`, con hora, nivel y mensaje:

```
2026-09-09 03:38:41  INFO     Partidas encontradas: 6
2026-09-09 03:42:50  WARNING  No se ha podido leer champions:all de Redis: Error -2 connecting to redis:6379. Name or service not known.
```

Se usa `INFO` para el curso normal, `WARNING` para lo que va mal pero no
impide seguir, como un reintento o Redis caído, y `ERROR` para lo que corta
la ejecución, como una clave no válida o la API de Riot inalcanzable.

Para leerlos:

- `docker compose logs -f api` los sigue en directo.
- `docker compose logs --tail 20 api` enseña las últimas 20 líneas, y con
  `--since 3h` en vez de `--tail 20`, las de las últimas 3 horas.
- `docker compose logs collector | grep WARNING` deja solo los problemas.

El logging se configura en `config.py`, que es lo primero que importan
`collector.py` y `api.py`. Hace falta configurarlo porque uvicorn solo ajusta
sus propios loggers.

Los logs se rotan con el bloque `x-logging` del `docker-compose.yml`, porque
un servicio que no termina nunca, como `api`, acabaría llenando el disco.
Los cambios ahí solo afectan a contenedores nuevos, así que hay que
recrearlos y luego se puede comprobar en uno:

```bash
docker compose up -d --force-recreate
docker inspect project0-api-1 --format "{{json .HostConfig.LogConfig}}"
```
