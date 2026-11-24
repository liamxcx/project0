# Tests and CI

English | [Español](../es/tests-y-ci.md)

## Tests

The tests are in `test_api.py` and `test_refresh.py`. The ones in
`test_api.py` use their own database and their own Redis, which are started
separately with `docker-compose.test.yml`:

```bash
docker compose -f docker-compose.test.yml up -d --wait db-test redis-test
docker compose -f docker-compose.test.yml run --rm flyway-test
source .venv/bin/activate
pytest
```

`--wait` waits for the database and Redis to be healthy, and `run` waits
for Flyway to create the tables. With a plain `up -d`, `pytest` could get
there first and fail with `relation "summoners" does not exist`. These are
the same commands the CI uses.

The containers stay up between runs, so running `pytest` is enough. The
`flyway-test` run has to be repeated after adding a migration, or the tests
run against the previous schema. To tear them down when you are done:

```bash
docker compose -f docker-compose.test.yml down
```

The test tools are in `requirements-dev.txt`, separate from
`requirements.txt`, because the latter is installed inside the image and
the application does not need them. How to set up the `.venv` is in
[development.md](development.md#requirements).

### How they work

FastAPI's `TestClient` calls the endpoints without starting uvicorn or
opening any port, so the tests take milliseconds. The only things that need
to be running are the test database and Redis.

`docker-compose.test.yml` is a separate Compose project, `project0-test`, so
it does not show up in the usual `docker compose ps`. The database uses port
5433 and Redis 6380, so they do not clash with the development ones. They
have no volume and use fixed credentials (`test`/`test`/`test`). Tearing
them down loses everything, and that way they work the same where there is
no `.env`, as in the CI.

`conftest.py`, which pytest loads before the tests, points `DB_HOST`,
`DB_PORT`, the credentials and `REDIS_URL` at those containers. Since
`load_dotenv()` does not overwrite variables that already exist, the tests
never reach the development database.

The `seeded_db` fixture empties the tables, inserts three made-up games and
empties them again at the end of the test, whether it passes or fails.
`full_match` adds a fourth one with all ten players, for the score, the
badges and the game details. There is deliberately little data, so that the
result of each test can be counted by hand.

The `disable_cache` fixture applies itself to every test and turns off the
cache, so the API always goes to the database. The tests that do want it are
marked with `@pytest.mark.with_cache`, and then they use `redis-test`, which
is emptied before and after. It is done this way round so that forgetting
the marker has no consequences. If the cache were on by default, a test
could receive the response the previous one left cached.

### What they cover and what they don't

Every endpoint has at least one test. `/ready` is tested with the test
database, which should return 200, and with the connection pointed at a
port where nothing is listening, which should return 503. The data includes
opponents without a `puuid`, one of them with a champion the followed
summoner also plays, so if the API's filter breaks it shows up in
`/matches`, `/patches`, `/summary` and `/champions`. The game details are
also tested with their ETag, the 304, gzip and a 404 that is not stored in
the browser.

Two tests check Redis. The first one calls `/matches`, deletes the games
from the database and calls it again, and the second response has to come
from the cache. The second one points the Redis client at a port where
nothing is listening and checks that `/matches` still responds from the
database.

Four tests check the metrics. The first one checks that `/metrics` responds
in the Prometheus text format. Two check that the counter is incremented
under the route template (`/matches/{match_id}`) and that URLs that do not
exist are grouped under `unmatched`. The last one checks that the series for
the refresh button's results exist from startup with a value of 0. They
compare against the value before the request and not against a fixed number,
because the counter lives in the process and also includes what other tests
added.

Eight tests cover the refresh button without a cluster, because `monkeypatch`
replaces the calls to the Kubernetes API with made-up lists of Jobs. The
three in `test_refresh.py` need neither the database nor Redis. They check
that the Job created is the one the admission policy accepts and that a
collector that is already running is detected. The five in `test_api.py`
check the cooldown, the 409, the status, that clearing the cache does not
remove the cooldown, and the 404 outside Kubernetes. Whether Kubernetes
really accepts the Job is tested in the cluster (see
[kubernetes.md](kubernetes.md#api-permissions)).

These tests do not use the `Dockerfile`. The CI's `build` job checks that
the image builds. No test checks that uvicorn starts inside the container.

The `.venv` uses the same Python version as the image (3.14). If they
drift apart, a test can pass locally and fail in the CI.

## CI

Every push, to any branch, runs the GitHub Actions pipeline defined in
`.github/workflows/ci.yml`. That way a change can be tested on a branch
before it reaches `main`.

It has four jobs. `lint`, `tests` and `chart-lint` start at the same time,
each on its own machine, and one failing does not stop the others, so a
formatting failure does not hide whether the tests pass. `build` waits for
all three to pass, so an image is never pushed if the code fails or if the
chart that will deploy it has errors.

### lint

It runs Ruff in two steps: `ruff format --check .` for the formatting,
without changing anything, and `ruff check .` for the lint rules. That way you
can see straight away which of the two failed.

Ruff is pinned in `requirements-dev.txt` so that the CI and every machine
use the same version, because the formatting rules change between
versions. Before a commit, `ruff format .` formats the code the way Ruff
expects. Ruff also checks the Python blocks in the `.md` files, so whatever
goes in a ```` ```python ```` block has to be valid Python.

### tests

The same commands as locally, with Python 3.14 like the image. It uses
`docker-compose.test.yml` and not GitHub Actions `services:`, to keep the
configuration in one place and because `services:` does not work for
containers that exit, such as `flyway-test`.

In the CI there is no `.env` and no secrets. `conftest.py` sets the
database and Redis variables, and the Riot ones are only required by
`collector.py`, which the tests do not run (see
[collector.md](collector.md#what-it-requests-from-riot)). That is why no
Riot key is stored in GitHub.

### chart-lint

```bash
helm lint --strict charts/project0
```

It checks that `Chart.yaml` is complete, that the templates render with the
values without errors and that the result is valid YAML. With `--strict`,
warnings also fail. It does not check that the chart works in a cluster,
only that it is well written. Helm is pinned to the same version as the one
used locally.

### build

It builds the project's three images with Docker's official actions. It is
a `matrix`, so the job is written once and GitHub runs one copy per image,
in parallel:

```
build (api)          Dockerfile              ghcr.io/liamxcx/project0
build (migrations)   migrations/Dockerfile   ghcr.io/liamxcx/project0-migrations
build (frontend)     frontend/Dockerfile     ghcr.io/liamxcx/project0-frontend
```

It is needed because the tests never use the `Dockerfile`, so a `COPY` of a
file that does not exist or a `pip install` that fails inside the image
would not show up anywhere else.

On `main` it builds them for amd64 and arm64 and pushes them to GitHub
Container Registry, with the short commit SHA as the tag. All three have
the same tag, so you know which migrations and which page go with which
code. On other branches it only builds them for amd64 and does not push
them, so the `No output specified with docker-container driver` warning in
the log is expected. The layers are stored in the Actions cache so that
what has not changed is not rebuilt. If one of the copies fails, GitHub
cancels the others.

### The runner's operating system

Every job uses `ubuntu-latest`, which GitHub moves to the next LTS version
when it comes out. It is left like that because Docker is the only thing
used from the system. Python and Helm are installed by `setup-python` and
`setup-helm` at the specified version, and everything else runs in
containers with a pinned image.

### The Actions

Each Action is pinned to a commit SHA, so it does not update on its own. To
upgrade it, find the commit of the new version in its repo and change the
SHA and the comment on that line:

```bash
git ls-remote --tags https://github.com/actions/checkout.git
```

If the version appears on two lines, the commit is the one ending in `^{}`.
The other one is the tag object, not the commit.
