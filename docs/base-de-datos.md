# Base de datos

PostgreSQL 16, con el esquema versionado con Flyway. En Compose los datos
viven en el volumen `datos_db`, que sobrevive a `docker compose down`. En el
clúster, en el disco de `postgres-0` (ver
[kubernetes.md](kubernetes.md#postgresql)).

## Las tablas

Seis tablas y una vista:

- `summoners` — traduce cada PUUID a un Riot ID legible, con su icono de
  perfil y su nivel
- `matches` — fecha, duración, tipo de cola y parche de cada partida
- `participants` — los diez jugadores de cada partida: campeón, posición,
  KDA, resultado, oro, daño hecho y recibido, CS, visión, objetos finales,
  hechizos de invocador, equipo, nivel, runas y su rango de Solo/Duo
- `item_purchases` — cada compra de cada jugador, con su minuto
- `skill_levelups` — cada subida de habilidad, con su minuto
- `ranked_snapshots` — un snapshot de la clasificatoria solo/duo en cada
  ejecución del collector: liga, división, LP, victorias, derrotas y el corte
  del siguiente escalón. Se guardan todos, y de ellos sale la gráfica de LP
  de los últimos 30 días
- `participant_scores` — la vista con la nota y el sello de cada jugador
  (ver [La nota y los sellos](#la-nota-y-los-sellos))

Todos esos datos, salvo el rango, vienen en la misma respuesta de MATCH-V5,
así que guardarlos no cuesta ninguna petición extra a Riot. Cómo los pide el
collector está en [collector.md](collector.md).

El CS va en dos columnas, `minions_killed` y `neutral_minions_killed`,
porque Riot lo da así. Sumarlas es cosa de la consulta:

```sql
SELECT champion, minions_killed + neutral_minions_killed AS cs
FROM participants;
```

Los campeones se guardan por su clave interna y los objetos y los hechizos
por su número. Los nombres y los iconos salen de Data Dragon en la página,
así que si Riot renombra un objeto el historial no se queda con un nombre que
ya no existe.

Para ver las partidas guardadas sin entrar en la base:

```bash
docker compose exec db psql -U loltest -d lolstats -P pager=off \
  -c "SELECT champion, kills, gold_earned, damage_to_champions FROM participants;"
```

## Los diez jugadores

`participants` guarda a los diez jugadores de cada partida. De los demás se
guarda todo lo de la partida y **nada de su identidad**, porque el PUUID
solo se rellena para los invocadores seguidos.

La clave primaria es `(match_id, participant_id)`, el número de jugador
dentro de la partida (1-10), que existe siempre. El `puuid` es opcional, y su
referencia a `summoners` no estorba, porque en SQL una clave ajena nula no se
comprueba. Buscar por `puuid` tiene su propio índice,
`idx_participants_puuid`, porque la clave primaria empieza por `match_id`.

Para enseñar el marcador hace falta un `LEFT JOIN` con `summoners`, porque
uno normal descartaría las nueve filas sin PUUID. Esas se muestran con el
nombre del campeón. Al añadir un invocador a los seguidos, sus filas
anteriores se rellenan con un `--refetch`.

`team_id` es 100 (azul) o 200 (rojo), como lo da Riot. Separa aliados de
rivales y permite calcular la participación en asesinatos, que necesita las
kills de todo el equipo.

## La nota y los sellos

Cada jugador de cada partida tiene una nota de 0 a 10, y el mejor de cada
equipo se lleva un sello: **MVP** en el equipo que gana y **BASTION** en el
que pierde.

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
sin que cueste nada. El daño recibido se descartó, porque recibir mucho no
dice por sí solo que se haya jugado bien.

Se calcula en la vista `participant_scores` (`V8`), que no guarda filas y se
calcula cada vez que se lee, así que siempre sale de lo que haya en
`participants`. Es una vista normal y no una materializada para no tener que
refrescarla después de cada ejecución del collector.

Reglas de los sellos:

- Solo hay uno por equipo. Si dos notas empatan, gana el `participant_id` más
  bajo, para que el resultado no cambie de una consulta a otra.
- Sin nota no hay sello. Las partidas guardadas antes de tener a los diez
  jugadores o el daño tienen esas columnas a `NULL`, y su nota también.
- La nota se redondea a un decimal al final, después de elegir el sello.
  Redondeando antes, un 7,46 y un 7,44 empatarían en 7,4.

`/matches` devuelve el sello del invocador en cada partida, y
`/matches/{match_id}` la nota y el sello de los diez jugadores.

## Borrar partidas

Las claves ajenas hacia `matches` tienen `ON DELETE CASCADE`, así que
borrar una partida se lleva sus participantes, sus compras y sus subidas
de habilidad:

```sql
DELETE FROM matches WHERE queue_id <> 420;
```

El mensaje de `DELETE` solo cuenta las filas de `matches`, y cada partida
arrastra cientos de filas en las otras tres tablas, así que conviene contar
antes de borrar.

La clave de `participants` hacia `summoners` no lleva cascade a propósito.
Quitar un invocador de los seguidos no debe borrar sus participaciones,
porque esas partidas siguen existiendo.

## El ciclo completo para añadir un dato

1. Escribir la migración con la columna nueva (`V12__...sql`)
2. Añadirla al `INSERT` del collector, en la lista de columnas, en los
   `%s` y en la tupla de valores
3. `docker compose up -d --build`, que aplica la migración y reconstruye
4. `--refetch` para rellenar el historial (ver
   [collector.md](collector.md#rellenar-datos-hacia-atrás))
5. Exponerla en `api.py` si la página la necesita

## Migraciones

El esquema vive en `migrations/`, un fichero por cambio. El nombre sigue la
convención de Flyway, con `V`, el número, **dos** guiones bajos y la
descripción. Con un solo guion el fichero se ignora.

Cada fichero lleva solo su cambio, no el esquema entero. El estado de la
base es el resultado de aplicarlos todos en orden.

### Cómo se aplican

En Compose, el servicio `flyway` se ejecuta al arrancar, aplica lo que falte
y termina. `collector` y `api` esperan a que acabe bien
(`service_completed_successfully`), así que si una migración falla la
aplicación no arranca, en vez de trabajar sobre una base a medias.

En el clúster las aplica el Job `migrations`, un hook de Helm que corre
antes de cada despliegue, con una imagen de Flyway que lleva los `.sql`
dentro (ver [kubernetes.md](kubernetes.md#desplegar-una-versión-nueva)).

Flyway lleva la cuenta en una tabla de la propia base,
`flyway_schema_history`, que se puede consultar como cualquier otra.

### Añadir un cambio

Crear el fichero con el número siguiente y levantar:

```bash
docker compose up -d
docker compose logs flyway
```

También se puede usar Flyway suelto, sin levantar nada, con
`docker compose run --rm flyway` seguido de una orden:

- `info` dice en qué versión está la base.
- `migrate` aplica lo que falte.
- `validate` comprueba que no ha cambiado ninguna migración ya aplicada.

### Una migración aplicada no se toca

Flyway guarda el checksum de cada fichero ejecutado y lo recalcula en cada
arranque. Cambiar una migración ya aplicada, aunque sea un comentario, da
error y no se ejecuta nada.

Si se pudiera editar una migración que lleva meses aplicada en producción,
un entorno nuevo ejecutaría la versión corregida y producción se quedaría
con la vieja, sin avisar a nadie. Para corregir algo se escribe la migración
siguiente.

### Meter Flyway en una base que ya existe

Si la base ya tiene las tablas, `migrate` intentaría ejecutar la V1 y
fallaría. Para eso está `flyway baseline -baselineVersion=1`, que crea la
tabla de control y apunta la V1 como aplicada sin ejecutarla. Desde ahí,
`migrate` sigue con la V2.

Se usó al introducir Flyway en el proyecto, sobre la base que ya tenía
partidas.

## Backups

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

Para ver qué tablas trae un backup sin restaurarlo:

```bash
kubectl exec -i -n project0 postgres-0 -- pg_restore --list < backups/<fichero>.dump | grep "TABLE DATA"
```

Para restaurarlo en una base vacía de Compose:

```bash
docker compose exec -T db sh -c 'pg_restore -U "$POSTGRES_USER" -d <base>' < backups/<fichero>.dump
```

Para restaurarlo en el clúster, sustituyendo lo que haya en `postgres-0`, y
aplicar después las migraciones escritas desde el backup:

```bash
kubectl exec -i -n project0 postgres-0 -- sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --single-transaction' < backups/<fichero>.dump
helm upgrade project0 charts/project0 -n project0 --wait --timeout 5m
```

El `helm upgrade` no cambia nada de la aplicación, pero lanza el hook de
las migraciones.

`--clean --if-exists` borra cada objeto del backup antes de crearlo, y
`--single-transaction` hace que, si algo falla, la base se quede como
estaba.

El backup va en formato custom de `pg_dump` y la carpeta `backups/` está
fuera de Git. Se hace a mano, y el backup automático está en
[MEJORAS.md](../MEJORAS.md).
