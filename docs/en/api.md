# API

English | [Español](../es/api.md)

The `api` service, built with FastAPI and served by uvicorn. It serves what
the collector has stored and never calls Riot, so looking at the statistics
does not use up any requests.

In Compose it listens on `http://localhost:8000`, published only on
`127.0.0.1`. In the cluster, everything except the internal routes is
published under `http://localhost/api/` (see
[kubernetes.md](kubernetes.md#cluster-ingress)).

## Endpoints

| Endpoint | What for | Parameters |
|---|---|---|
| `GET /health` | Says the process is responding, without querying anything. It is the liveness probe in Kubernetes | |
| `GET /ready` | Runs a `SELECT 1` against PostgreSQL and returns 503 if it does not respond. It is the readiness probe | |
| `GET /metrics` | The metrics for Prometheus, in its text format. It does not appear in `/docs` (see [monitoring.md](monitoring.md#api-metrics)) | |
| `GET /summoners` | The followed summoners, with their profile icon and level | |
| `GET /matches` | The match history, 10 at a time, from newest to oldest, with the [MVP or BASTION](database.md#the-score-and-the-badges) badge. The response has the form `{"matches": [...], "has_more": true}`, and `has_more` says whether there are more | `patch`, `champion`, `offset` |
| `GET /matches/{match_id}` | The details of a game: the followed summoner's statistics and the ten players with their score, scoreboard line, level, runes, rank, purchases with their minute and skill order. 404 if it does not exist | |
| `GET /patches` | The patches that have games and how many each one has, from newest to oldest | |
| `GET /summary` | Games, wins, losses and winrate for the season or for a patch | `patch` |
| `GET /rank` | The latest solo/duo ranked snapshot: tier, division, LP, season record and the cutoff for the next tier. `null` if there is none | |
| `GET /rank/history` | The last snapshot of each of the last 30 days, for the LP chart. `ladder_lp` is the LP counted from Iron IV, so that moving up a division does not look like a drop | |
| `GET /champions` | Per-champion statistics for the season or for a patch, from most to least played. `kda_ratio` comes from the totals and not from the rounded averages, and is `null` if there are no deaths | `patch` |
| `GET /refresh` | Whether a collector is running and how many seconds are left before another one can be started, as `{"running": false, "retry_after": 0}` | |
| `POST /refresh` | Starts the collector. 202 with the Job name, 409 if one is already running and 429 if the cooldown has not passed (see [Refreshing from the page](#refreshing-from-the-page)) | |

The parameters are optional and can be combined, for example
`/matches?patch=26.17&champion=Ahri&offset=10`:

- `patch` is the patch as the player sees it (`26.17`). Without it,
  `/summary` and `/champions` use the current season and `/matches` returns
  all games.
- `champion` is Riot's internal key (`Kaisa`, `MonkeyKing`) and is
  case-sensitive.
- `offset` is how many games to skip. With `0` you get the first 10 and with
  `10` the next ones. A negative number returns 422.

`next_cutoff_lp`, in `/rank`, is the LP needed to move up from Master or
Grandmaster. Riot recalculates it every day, so it changes even if the
summoner does not play.

Every data endpoint filters on `puuid IS NOT NULL`. `participants` stores
the ten players of each game and only the followed summoners have a PUUID,
so without that filter the aggregates would include opponents and
teammates. When there are several followed summoners, a parameter will be
needed to choose which one.

## Patch and season

`game_version` is Riot's internal numbering, the one its API returns. It
does not match what the player sees in the client, because the first number
of the public one is ten higher (internal `16.17` = public `26.17`). Each
internal series corresponds to a calendar year. The API does the conversion
at query time, and only the original value is stored in the database.

Riot does not provide the season reliably, so it is derived from the first
number of the internal version (`16` in 2026). The current season is the
season of the most recent game.

`/summary` and `/rank` get wins and losses in different ways. `/summary`
counts them in the stored games, which only go back to when the collector
started. `/rank` copies them from Riot, which has the whole season, so the
season record comes from `/rank`.

## Redis cache

The data endpoints are cached in Redis, each with its own key. `/health`,
`/ready` and `/metrics` are not cached. Empty responses are stored too. A
game that does not exist is kept in Redis as `null`, and the API returns 404
without querying PostgreSQL again.

Each key is prefixed with `cache:` and the API version, which is its image
tag, as in `cache:913b445:match:EUW1_…`, and `cache:dev:` in Compose. During
a rolling update, pods of both versions run at the same time, and this way
neither reads what the other stored in a different format. The keys of the
old version expire on their own with the TTL.

When it finishes, the collector deletes every key that starts with `cache:`
(`api_cache.py`), so the page sees the new data straight away and not when
the TTL expires. The refresh button's cooldown is in a separate key,
`refresh:cooldown`, which is why it is not deleted.

Redis is optional. Cache calls are wrapped in `cache_get` and `cache_set`,
which catch any error and treat it as "nothing cached", so the API returns
the same response, only more slowly, and logs a warning. The client also has
`socket_timeout=1`, so that a Redis that accepts the connection but does not
reply does not leave the request waiting. A test checks that the API
responds with Redis down (see [tests-and-ci.md](tests-and-ci.md)).

## Refreshing from the page

`POST /refresh` starts the collector without waiting for its scheduled
time. The API creates a Job from the `collector` CronJob, the same as
`kubectl create job --from`, and talks to the Kubernetes API using
`requests` (`refresh.py`). It does not use the official Kubernetes library,
which added about 90 MB to the image and, by passing the CronJob through its
models, could lose fields and cause the admission policy to reject the Job.
The permissions and the policy are in
[kubernetes.md](kubernetes.md#api-permissions).

There is a 5-minute cooldown between refreshes (`REFRESH_COOLDOWN_SECONDS`),
because a run with new games uses up a good part of the Riot quota. The
cooldown is stored in Redis with `SET NX`, so two simultaneous requests
cannot each start a collector. If no collector ends up being started,
because one is already running or because Kubernetes fails, the cooldown is
removed. Without Redis, `POST /refresh` returns 503, because without the
cooldown there is no way to protect the quota.

It only works in Kubernetes. Outside the cluster `REFRESH_ENABLED` is not
set, and both endpoints return 404, which does not count as an error in
the alerts.

## ETag and gzip

On top of Redis, `/matches/{match_id}` has an ETag, a hash of the JSON, and
`Cache-Control: no-cache`. The browser stores the details but checks with
the API before using them, and if they have not changed the API returns 304
with no body. This way it never uses a stale copy after a deployment that
changes the response. The 404 has none of this, because the game may arrive
on the next collector run.

Responses of 500 bytes or more are compressed with gzip when the client
asks for it, with FastAPI's `GZipMiddleware`. It is done in the API and not
in nginx or Traefik so that it works the same in Compose and in the cluster.
The details of a game go from about 13 KB to about 2 KB.

## Trying it out

FastAPI generates the documentation automatically from the registered routes,
at `http://localhost:8000/docs`, and the raw schema at
`http://localhost:8000/openapi.json`. On each endpoint in `/docs`,
*Try it out* and *Execute* call the real API and show the JSON it returns.

From the terminal:

```bash
curl http://localhost:8000/health
curl -s "http://localhost:8000/matches?patch=26.21&champion=Yunara" | python3 -m json.tool
curl -s http://localhost:8000/rank | python3 -m json.tool
```
