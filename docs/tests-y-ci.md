# Tests y CI

## Tests

Los tests están en `test_api.py` y `test_refresh.py`. Los de `test_api.py`
usan su propia base de datos y su propio Redis, que se levantan aparte con
`docker-compose.test.yml`:

```bash
docker compose -f docker-compose.test.yml up -d --wait db-test redis-test
docker compose -f docker-compose.test.yml run --rm flyway-test
source .venv/bin/activate
pytest
```

`--wait` espera a que la base y Redis estén sanos, y `run` espera a que
Flyway cree las tablas. Con un `up -d` a secas, `pytest` podría llegar antes
y fallar con `relation "summoners" does not exist`. Son los mismos comandos
que usa el CI.

Los contenedores se quedan levantados entre ejecuciones, así que basta con
lanzar `pytest`. El `run` de `flyway-test` hay que repetirlo después de
añadir una migración, porque si no los tests corren contra el esquema
anterior. Para tirarlos al acabar:

```bash
docker compose -f docker-compose.test.yml down
```

Las herramientas de test están en `requirements-dev.txt`, aparte de
`requirements.txt`, porque este último se instala dentro de la imagen y la
aplicación no las necesita. Cómo preparar el `.venv` está en
[desarrollo.md](desarrollo.md#requisitos).

### Cómo funcionan

`TestClient` de FastAPI llama a los endpoints sin levantar uvicorn ni abrir
ningún puerto, así que los tests tardan milisegundos. Lo único que tiene que
estar arrancado son la base y el Redis de test.

`docker-compose.test.yml` es un proyecto de Compose aparte, `project0-test`,
así que no sale en el `docker compose ps` de siempre. La base va en el 5433
y Redis en el 6380, para no chocar con los de desarrollo, sin volumen y con
credenciales fijas (`test`/`test`/`test`). Al tirarlos se pierde todo, y así
funcionan igual donde no hay `.env`, como en el CI.

`conftest.py`, que pytest carga antes que los tests, apunta `DB_HOST`,
`DB_PORT`, las credenciales y `REDIS_URL` a esos contenedores. Como
`load_dotenv()` no sobrescribe variables que ya existen, los tests nunca
llegan a la base de desarrollo.

La fixture `seeded_db` vacía las tablas, mete tres partidas inventadas y las
vuelve a vaciar al acabar el test, pase o falle. `full_match` añade una
cuarta con los diez jugadores, para la nota, los sellos y el detalle. Son
pocos datos a propósito, para que el resultado de cada test se pueda contar
a mano.

La fixture `disable_cache` se aplica sola a todos los tests y apaga la
caché, así que la API va siempre a la base. Los tests que sí la quieren
llevan `@pytest.mark.with_cache`, y entonces usan `redis-test`, que se vacía
antes y después. Está así, y no al revés, para que olvidar el marker no
tenga consecuencias. Si la caché estuviera encendida por defecto, un test
podría recibir la respuesta que dejó cacheada el anterior.

### Qué cubren y qué no

Todos los endpoints tienen al menos un test. `/ready` se prueba
con la base de test, que debe dar 200, y con la conexión apuntada a un puerto
donde no escucha nadie, que debe dar 503. Entre los datos hay rivales sin
`puuid`, uno de ellos con un campeón que también lleva el invocador seguido,
así que si el filtro de la API se rompe se nota en `/matches`, `/patches`,
`/summary` y `/champions`. El detalle de partida se prueba además con su
ETag, el 304, gzip y un 404 que no se guarda en el navegador.

Dos tests comprueban Redis. El primero llama a `/matches`, borra las
partidas de la base y vuelve a llamar, y la segunda respuesta tiene que
salir de la caché. El segundo apunta el cliente de Redis a un puerto donde no
escucha nadie y comprueba que `/matches` responde igual desde la base.

Cuatro tests comprueban las métricas. El primero mira que `/metrics` responda
en el formato de texto de Prometheus. Dos miran que el contador sume en la
plantilla de la ruta (`/matches/{match_id}`) y que las URL que no existen
vayan juntas en `unmatched`. El último mira que los resultados del botón de
actualizar existan desde el arranque, con 0. Comparan con el valor de antes
de la petición y no con un número fijo, porque el contador vive en el
proceso y suma también lo de otros tests.

Ocho prueban el botón de actualizar sin clúster, porque `monkeypatch`
sustituye las llamadas a la API de Kubernetes por listas de Jobs inventadas.
Los tres de `test_refresh.py` no necesitan ni base ni Redis. Comprueban que el
Job que se crea es el que acepta la política de admisión y que se detecta si
ya hay un collector en marcha. Los cinco de `test_api.py` comprueban la
espera, el 409, el estado, que vaciar la caché no quita la espera y el 404
fuera de Kubernetes. Que Kubernetes acepte el Job de verdad se prueba en el
clúster (ver [kubernetes.md](kubernetes.md#permisos-de-la-api)).

Estos tests no usan el `Dockerfile`. Que la imagen se construya lo
comprueba el job `build` del CI. Que uvicorn arranque dentro del contenedor
no lo comprueba ningún test.

El `.venv` usa la misma versión de Python que la imagen (3.14). Si se
separan, un test puede pasar en local y fallar en el CI.

## CI

Cada push, a cualquier rama, ejecuta el pipeline de GitHub Actions definido
en `.github/workflows/ci.yml`. Así un cambio se puede probar en una rama
antes de que llegue a `main`.

Tiene cuatro jobs. `lint`, `tests` y `chart-lint` arrancan a la vez, cada uno
en su propia máquina, y que falle uno no para a los otros, así que un fallo
de formato no esconde si los tests pasan. `build` espera a que pasen los
tres, para no subir nunca una imagen si el código falla o si el chart que la
va a desplegar tiene errores.

### lint

Pasa Ruff en dos pasos, `ruff format --check .` para el formato, sin
cambiar nada, y `ruff check .` para el linter. Así se ve a la primera cuál
de los dos ha fallado.

Ruff está fijado en `requirements-dev.txt` para que el CI y cualquier
máquina usen la misma versión, porque entre versiones cambian las reglas de
formato. Antes de un commit, `ruff format .` deja el código como lo quiere.
Ruff revisa también los bloques de Python de los `.md`, así que lo que vaya
en un bloque ```` ```python ```` tiene que ser Python válido.

### tests

Los mismos comandos que en local, con Python 3.14 como la imagen. Usa
`docker-compose.test.yml` y no los `services:` de GitHub Actions, para tener
la configuración en un solo sitio y porque `services:` no sirve para
contenedores que terminan, como `flyway-test`.

En el CI no hay `.env` ni secretos. `conftest.py` pone las variables de la
base y de Redis, y las de Riot solo las exige `collector.py`, que los tests
no ejecutan (ver [collector.md](collector.md#qué-pide-a-riot)). Por eso no
hay ninguna clave de Riot guardada en GitHub.

### chart-lint

```bash
helm lint --strict charts/project0
```

Comprueba que `Chart.yaml` está completo, que los templates se rellenan con
los values sin errores y que el resultado es YAML válido. Con `--strict`
fallan también los avisos. No comprueba que el chart funcione en un clúster,
solo que está bien escrito. Helm va fijado a la misma versión que en local.

### build

Construye las tres imágenes del proyecto con las acciones oficiales de
Docker. Es un `matrix`, así que el job se escribe una vez y GitHub lanza una
copia por imagen, a la vez:

```
build (api)          Dockerfile              ghcr.io/liamxcx/project0
build (migrations)   migrations/Dockerfile   ghcr.io/liamxcx/project0-migrations
build (frontend)     frontend/Dockerfile     ghcr.io/liamxcx/project0-frontend
```

Hace falta porque los tests nunca usan el `Dockerfile`, así que un `COPY` de
un fichero que no existe o un `pip install` que falla dentro de la imagen no
saldría en ningún otro sitio.

En `main` las construye para amd64 y arm64 y las sube a GitHub Container
Registry, con el SHA corto del commit como tag. Las tres llevan el mismo
tag, así que se sabe qué migraciones y qué página van con qué código. En el
resto de ramas solo las construye para amd64 y no las sube, así que el aviso
`No output specified with docker-container driver` del log es esperado.
Las capas se guardan en la caché de Actions para no reconstruir lo que no
ha cambiado. Si falla una de las copias, GitHub cancela las demás.

### El sistema del runner

Todos los jobs usan `ubuntu-latest`, que GitHub mueve a la siguiente
versión LTS cuando sale. Se deja así porque del sistema solo se usa Docker.
Python y Helm los instalan `setup-python` y `setup-helm` en la versión
indicada, y lo demás va en contenedores con la imagen fijada.
