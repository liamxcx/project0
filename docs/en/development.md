# Development with Compose

English | [Español](../es/desarrollo.md)

Compose is the development environment. It starts the application's
services on the local machine, with the page and the nginx configuration
mounted from disk, so a change to the page shows up after reloading the
browser. The cluster is covered in [kubernetes.md](kubernetes.md).

## Requirements

- Docker
- A Riot API key: https://developer.riotgames.com.
  The Development Key expires every 24 hours. A personal key, which you get
  by registering the project on the portal, does not expire.
- Python 3.14, to run the tests locally (see
  [tests-and-ci.md](tests-and-ci.md)). It is the same version as the image:

```bash
python3.14 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
```

## Configuration

Copy `.env.example` to `.env` and fill in the values.

The Riot ID is split in two. If your Riot ID is `YourName#EUW`, the name goes in
`RIOT_GAME_NAME` and the tag in `RIOT_TAG_LINE`, without the hash sign.

`MATCH_COUNT` is how many recent games are requested from Riot on each run.
It defaults to 20. Since the collector does not request the games it
already has, raising it only costs extra requests the first time.

`TZ` is the containers' time zone, and the one shown in the logs. It is set
to Madrid time rather than `UTC` so the logs can be read without converting
the time.

`CACHE_TTL_SECONDS` is how many seconds each response is kept in the cache.
It is the maximum lag between what is in PostgreSQL and what the API
returns. Raising it takes load off PostgreSQL at the cost of serving older
data.

`DB_HOST` is `db` inside Compose. In the cluster it is `postgres`, set by
the `project0-config` ConfigMap. To run the collector or the API outside
Docker, set it to `localhost`.

`DB_PORT` is not in the `.env` and defaults to 5432. Only the tests change
it, since they use their own database on 5433.

Variables without a default value go through `required_env()`, which stops
execution with a clear message if they are missing. Without it, a missing
variable ends up as the text `None` inside the connection string, and the
error shows up later, when connecting, saying the password is wrong when in
fact there is none.

## Running

```bash
docker compose up
```

This starts the six services. `flyway` applies the schema before
`collector` and `api` start, and the API also waits for Redis to be healthy.

The services do not all behave the same way:

- `db`, `redis`, `api` and `frontend` are long-running processes that keep
  running until they are stopped.
- `collector` and `flyway` exit when their work is done. In
  `docker compose ps` they show as `Exited (0)`, which is not an error.

The collector runs once on `up`, and after that by hand:

```bash
docker compose run --rm collector
```

The page does not show the refresh button, because it works by creating a
Kubernetes Job and there is no Kubernetes in Compose. Use this command to
refresh instead.

Which command to use depending on what you changed:

- After changing `docker-compose.yml` or the `.env`, or adding a migration,
  `docker compose up` is enough.
- After a change to the code or to `requirements.txt`, you need
  `docker compose up --build`.

`--build` is needed because the `.py` files and `requirements.txt` are
copied into the image. The `.env` and the migrations are read at startup,
so they do not need it.

Do not name a single service when using `--build`. `collector` and `api`
share the `Dockerfile`, but Compose builds one image per service, so `docker
compose up --build api` rebuilds only that one and leaves the other with the
old code, without any error. Naming a service is useful for starting it on
its own, not for rebuilding.

When the API is recreated, Compose also restarts `frontend`, because its
nginx needs the new IP of the API (see [frontend.md](frontend.md)).

Schema changes do not need `down -v`. They are written as a new migration
and `flyway` applies it at startup without touching the data (see
[database.md](database.md#migrations)).

`api` starts uvicorn with `--host 0.0.0.0`. By default uvicorn listens on
`127.0.0.1`, which inside the container means only the container itself, so
the port would be published with nothing listening behind it.

## Logs

Everything is logged with `logging`, with the time, the level and the
message. The messages are in Spanish:

```
2026-09-09 03:38:41  INFO     Partidas encontradas: 6
2026-09-09 03:42:50  WARNING  No se ha podido leer champions:all de Redis: Error -2 connecting to redis:6379. Name or service not known.
```

`INFO` is used for normal operation, `WARNING` for things that go wrong but
do not stop execution, such as a retry or Redis being down, and `ERROR` for
things that stop execution, such as an invalid key or the Riot API being
unreachable.

To read them:

- `docker compose logs -f api` follows them live.
- `docker compose logs --tail 20 api` shows the last 20 lines, and with
  `--since 3h` instead of `--tail 20`, those from the last 3 hours.
- `docker compose logs collector | grep WARNING` keeps only the problems.

Logging is configured in `config.py`, which is the first thing
`collector.py` and `api.py` import. It has to be configured because uvicorn
only sets up its own loggers.

Logs are rotated with the `x-logging` block in `docker-compose.yml`,
because a service that never exits, such as `api`, would end up filling the
disk. Changes there only apply to new containers, so they have to be
recreated, and then you can check one of them:

```bash
docker compose up -d --force-recreate
docker inspect project0-api-1 --format "{{json .HostConfig.LogConfig}}"
```
