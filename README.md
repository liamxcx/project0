# Proyecto 0

Herramienta personal de estadísticas de League of Legends.
Consume la API de Riot Games y guarda el historial de partidas en PostgreSQL.

Proyecto de aprendizaje: el objetivo es llegar a una aplicación
contenerizada con base de datos, API propia y frontend.

Solo se procesan partidas de Ranked Solo/Duo (queueId 420).

## Estado actual

La aplicación, dado un Riot ID:

1. Obtiene el PUUID de la cuenta (ACCOUNT-V1)
2. Lista los identificadores de las últimas partidas de ranked (MATCH-V5)
3. Descarga el detalle de cada partida
4. Guarda invocador, partida y participación en PostgreSQL sin duplicar

Incluye reintentos ante fallos de red y control del límite de peticiones.
El arranque está ordenado: la aplicación espera a que PostgreSQL esté
listo para aceptar conexiones.

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
```

El Riot ID va separado: si eres `TuNombre#EUW`, el nombre va en
`RIOT_GAME_NAME` y el tag en `RIOT_TAG_LINE`, sin almohadilla.

`DB_HOST` es `db` dentro de Compose. Para ejecutar el script fuera de
Docker hay que ponerlo a `localhost`.

## Ejecución

```bash
docker compose up
```

Levanta la aplicación y PostgreSQL. El esquema de `schema.sql` se aplica
automáticamente la primera vez que se inicializa la base de datos.

Qué comando usar según lo que hayas cambiado:

```bash
docker compose up            # cambios en docker-compose.yml o .env
docker compose up --build    # cambios en main.py o requirements.txt
docker compose down -v       # cambios en schema.sql (borra los datos)
```

El `--build` hace falta porque `main.py` y `requirements.txt` se copian
dentro de la imagen. El resto se lee al arrancar.

El `-v` hace falta con `schema.sql` porque el script solo se ejecuta
cuando la base de datos está vacía. Más adelante habría que sustituirlo
por migraciones para no perder el historial.

## Base de datos

Tres tablas:

- `invocadores` — traduce cada PUUID a un Riot ID legible
- `partidas` — fecha, duración y tipo de cola de cada partida
- `participaciones` — campeón, posición, KDA y resultado de un invocador
  en una partida

Las inserciones usan `ON CONFLICT DO NOTHING`, así que el script se puede
ejecutar las veces que haga falta: solo guarda lo que no tenía.

Los datos viven en el volumen `datos_db`, que sobrevive a `docker compose down`.

Para ver las partidas guardadas sin entrar en la base de datos:

```bash
docker compose exec db psql -U lol -d lolstats -c "SELECT * FROM participaciones;"
```

## Estructura

```
main.py              lógica de la aplicación
schema.sql           definición de las tablas
Dockerfile           imagen de la aplicación
docker-compose.yml   orquestación de los servicios
requirements.txt     dependencias de Python
```

## Notas

Las rutas usan hosts distintos según la API. Las que usa este proyecto
(ACCOUNT-V1 y MATCH-V5) van por región grande: `europe.api.riotgames.com`.
Otras, como LEAGUE-V4 para el rango, usan la plataforma:
`euw1.api.riotgames.com`.

Dentro de la red de Compose los servicios se alcanzan por su nombre de
servicio, no por `localhost`.

El servicio `db` tiene un healthcheck con `pg_isready`, y `app` usa
`depends_on` con `condition: service_healthy`. Sin eso, `depends_on`
solo esperaría a que el contenedor arrancase, no a que PostgreSQL
aceptase conexiones, y la aplicación podría fallar al conectar.

Códigos de error habituales de la API:

- `401` / `403` — clave inválida o caducada, hay que regenerarla
- `404` — Riot ID incorrecto
- `429` — límite de peticiones superado (el script espera y reintenta)

Tras regenerar la clave puede tardar unos segundos en ser válida.

## Pendiente

- Migraciones para modificar el esquema sin perder datos
- API propia con FastAPI
- Caché con Redis y actualización programada
- Frontend para visualizar las estadísticas
- Despliegue en Kubernetes