# Collector

`collector.py` arranca, pide a Riot lo que le falta, lo guarda en PostgreSQL
y termina. En el clúster lo lanza un CronJob cada hora (ver
[kubernetes.md](kubernetes.md#collector)). En Compose se ejecuta una vez al
hacer `up`, y después a mano con `docker compose run --rm collector`.

## Qué pide a Riot

Dado un Riot ID, en cada ejecución:

| API de Riot | Para qué |
|---|---|
| ACCOUNT-V1 | El PUUID del invocador |
| SUMMONER-V4 | Su icono de perfil y su nivel |
| LEAGUE-V4 | Un snapshot de su clasificatoria de Solo/Duo y el rango de los otros nueve jugadores de cada partida |
| MATCH-V5 | La lista de sus últimas partidas y, de cada una, el detalle y el timeline |

Antes de descargar, consulta cuáles de la lista ya están en la base y se las
salta, así que solo pide a Riot lo que le falta. Cada partida se guarda en su
propia transacción. Si una falla, se salta, las demás se guardan y la
siguiente ejecución la vuelve a intentar.

Las rutas usan hosts distintos según la API. ACCOUNT-V1 y MATCH-V5 van por
región grande, `europe.api.riotgames.com`. LEAGUE-V4 y SUMMONER-V4 van por
plataforma, `euw1.api.riotgames.com`.

El rango de cada jugador es una petición por jugador. Son nueve más por
partida, porque el del invocador seguido ya se pide para `ranked_snapshots`.
Dentro de una misma ejecución se reutiliza si el jugador sale en varias
partidas. Es el rango del momento en que se guarda la partida, porque Riot no
da el que tenía al jugarla. Se pide con su PUUID, pero solo se guarda el
rango.

Las tres variables de Riot (`RIOT_API_KEY`, `RIOT_GAME_NAME` y
`RIOT_TAG_LINE`) se leen en `collector.py` y no en `config.py`. Importar
`config.py` ejecuta el fichero entero, así que si estuvieran ahí la API no
arrancaría sin ellas aunque no las use, y tampoco se podrían lanzar los tests
sin un `.env`.

## Solo ranked solo/duo

El collector pide a Riot únicamente los identificadores de esa cola
(`queue=420` en la lista de MATCH-V5). El filtro va en la petición y no al
guardar, así que las partidas de otros modos ni se descargan. Sin él, Riot
devuelve las últimas partidas de cualquier tipo y las normales y los
swiftplay acaban mezclados con las ranked, falseando todas las medias.

`RANKED_SOLO_QUEUE` está en `config.py` y no en el `.env` porque no es
configuración que cambie según el entorno. El proyecto entero se define
sobre esa cola, y cambiarla dejaría sin sentido lo que ya está guardado.

`matches.queue_id` se sigue guardando aunque hoy valga siempre 420, porque
es el dato tal como viene de Riot. La API no lo expone.

## El timeline

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

La respuesta pesa cerca de 1 MB, así que no se guarda entera. Extraer los
cuatro campos que importan la deja en unos 19 KB por partida, cincuenta
veces menos.

Tres cosas que hace el collector al procesarlo:

- **Descarta los eventos con `participantId` 0.** Los jugadores van del 1
  al 10, y los del 0 son artefactos del arranque de la partida.
- **Aplica los `ITEM_UNDO`.** Comprar algo y deshacerlo en la tienda genera
  un evento de compra y otro de deshacer. Sin esto, el primer objeto de una
  build podría ser uno que se devolvió.
- **Borra antes de insertar.** La clave de estas tablas es un id
  automático, así que un `--refetch` duplicaría las filas en vez de
  reemplazarlas.

Los jugadores se identifican por su número dentro de la partida (1-10), no
por PUUID. Para analizar builds basta, y así no se guarda la identidad de
nadie más. `participants.participant_id` es ese mismo número, así que las
compras de cualquiera de los diez salen cruzando las dos tablas.

## Insertar sin duplicar

Las inserciones usan `ON CONFLICT ... DO UPDATE`. Si la fila no está se
inserta, y si está se actualiza con los valores nuevos, así que el collector
se puede ejecutar las veces que haga falta y el resultado es siempre el
mismo. `DO NOTHING` no valdría, porque ignoraría la fila entera y nunca se
podrían rellenar columnas añadidas más tarde.

Los valores que vienen de Riot se pasan a la consulta como parámetros (`%s`
y una tupla), nunca interpolados en el texto SQL.

## Rellenar datos hacia atrás

El collector se salta las partidas que ya tiene, para no gastar peticiones.
Con `--refetch` las vuelve a pedir y reescribe las filas:

```bash
docker compose run --rm collector python collector.py --refetch
```

Hace falta al añadir una columna nueva (las partidas viejas la tendrían a
`NULL`) y al corregir un fallo del collector que haya guardado algo mal.

Solo vuelve a pedir las partidas de la lista que da Riot, que mide
`MATCH_COUNT` (20 por defecto). Para llegar más atrás se sube solo para esa
ejecución, sin tocar el `.env`:

```bash
docker compose run --rm -e MATCH_COUNT=70 collector python collector.py --refetch
```

Así también se bajan las partidas que nunca se guardaron. En Compose el
collector solo corre con `up`, y si entre dos ejecuciones se juegan más de
`MATCH_COUNT` partidas, las más antiguas de ese tramo se quedan sin bajar.

La lista de Riot da como mucho cien partidas por petición y el collector
no pide más, así que las anteriores no se pueden volver a pedir y una
columna añadida tarde se queda con `NULL` para siempre en esas.

En el clúster el `--refetch` se lanza con un Job a mano (ver
[kubernetes.md](kubernetes.md#collector)).

## Rate limit y errores

Todas las peticiones pasan por `fetch()`, con un límite de 15 segundos cada
una. Con un fallo de red, un 5xx o un 429, la petición se intenta hasta tres
veces. Entre intentos espera 1, 2 y 4 segundos, o lo que diga la cabecera
`Retry-After` si es un 429.

Códigos de error habituales de Riot:

- `401` / `403` — la clave no es válida
- `404` — Riot ID incorrecto
- `429` — rate limit superado, el collector espera y reintenta

Tras regenerar la clave puede tardar unos segundos en ser válida.
