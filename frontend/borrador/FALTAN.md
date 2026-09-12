# Datos que la maqueta necesita y la API no tiene

Una línea por dato. Cuando uno se implementa, se borra de aquí y se
documenta en `DATOS.md`.

Formato:

- **`nombre_del_dato`** — para qué se usa en la maqueta. De dónde saldría:
  de Riot (MATCH-V5), calculado en SQL, o derivado en el frontend.

Aviso: añadir un dato de Riot suele significar una columna nueva en
`participants` o en `matches`, y hoy cambiar `schema.sql` obliga a
`docker compose down -v`, que borra el historial. Si la lista crece, toca
resolver antes lo de las migraciones.

---

## Pendientes

### Identidad del jugador (no hay endpoint hoy)

La maqueta enseña al jugador por todas partes (buscador, cabecera, nombre en
rojo dentro del marcador 5v5) y la API no devuelve nada de esto: `DATOS.md`
solo tiene `/health`, `/matches` y `/champions`.

- **`game_name`, `tag_line`** — el Riot ID "Charli xcx#Wink" del buscador, de la
  barra superior y de la fila propia en la pestaña Equipos. De Riot
  (ACCOUNT-V1, `/riot/account/v1/accounts/by-puuid/{puuid}`); columnas en
  `summoners`. Haría falta un `GET /summoner` que los exponga.
- **`puuid`** — clave para atar todo lo demás. Ya existe en la base; hoy no sale
  por la API.
- **`platform` / región** — el "· EUW" junto al nombre y el "EUW · Master" de
  las búsquedas recientes. Es configuración del colector; basta con exponerla.
- **`profile_icon_id`, `summoner_level`** — la maqueta hoy dibuja iniciales
  ("CX") porque no hay icono de perfil. De Riot (SUMMONER-V4); columnas en
  `summoners`. Iconos en Data Dragon (`img/profileicon`).
- **búsqueda de otro invocador** — DECIDIDO: no habrá buscador abierto. El
  proyecto seguirá a una lista corta y fija de invocadores (el propio y cinco o
  seis amigos), configurada de antemano y recolectada por el `scheduler` en
  cada vuelta. En la maqueta debe ser un desplegable, o un campo con
  autocompletado sobre esa lista, nunca texto libre: un campo abierto promete
  consultar a cualquiera y eso no va a existir. Se descartó la recolección bajo
  demanda (22 peticiones y 10-30 s por invocador nuevo, que obligaría a montar
  cola y trabajo en segundo plano). Llega en `m3`.
- **búsquedas recientes** — con la decisión anterior dejan de tener sentido como
  historial de búsquedas; si se quieren, son los invocadores seguidos.
- **rango de cada invocador seguido** — para enseñar tier junto a cada nombre
  del desplegable hace falta `tier`, del bloque siguiente.

### Cabecera del jugador

- **`tier`, `division`, `league_points`** — tarjeta de clasificatoria: "Master
  700 LP" y la barra de progreso hacia el siguiente escalón. De Riot
  (LEAGUE-V4, `/lol/league/v4/entries/by-puuid/{puuid}`); tabla nueva
  `ranked_entries` o columnas en `summoners`.
- **`gm_cutoff_lp`** — el corte de Gran Maestro de la región, para el "faltan
  1.100 LP" de la barra. De Riot (LEAGUE-V4, `challengerleagues`/
  `grandmasterleagues`); solo aplica a Master+.
- **`ranked_wins`, `ranked_losses`** — el "13V 7D" y el winrate de la tarjeta de
  clasificatoria. Hoy la maqueta los calcula con las 20 partidas guardadas, que
  no es el balance de la temporada. De Riot (LEAGUE-V4, misma entrada que
  `tier`).
- **`lp_delta`** por partida — el "+23 / −18" del desplegable de cada partida.
  Riot no lo da: se derivaría en SQL comparando el LP de dos capturas
  consecutivas del colector, así que exige guardar histórico de LP.

### Detalle de partida (desplegable)

- **`total_damage_dealt_to_champions`** — cifra de daño del resumen y barra de
  cuota de daño. De Riot (MATCH-V5, participante); columna en `participants`.
- **`gold_earned`** — oro total y oro/min de la pestaña Objetos. De Riot
  (MATCH-V5); columna en `participants`. El oro/min se deriva en el frontend
  con `duration_seconds`.
- **`total_minions_killed` + `neutral_minions_killed`** — CS y CS/min. De Riot
  (MATCH-V5); dos columnas en `participants`, se suman en SQL.
- **`total_damage_taken`** — daño recibido del resumen. De Riot (MATCH-V5);
  columna en `participants`.
- **`vision_score`, `wards_placed`** — puntuación de visión y guardianes
  puestos. De Riot (MATCH-V5); dos columnas en `participants`.
- **`kill_participation`** — porcentaje de participación en asesinatos. De Riot
  viene en `challenges.killParticipation`; alternativa: calcularlo en SQL como
  `(kills + assists) / kills_del_equipo`, que hoy no se puede porque no se
  guarda al resto del equipo.
- **`item0`…`item6`** — los seis objetos finales y los hechizos de invocador
  (`summoner1_id`, `summoner2_id`). De Riot (MATCH-V5); columnas en
  `participants`. Los iconos salen de Data Dragon (`img/item`, `img/spell`).
- **`build_order`** — orden de compra por componentes con su minuto (la línea de
  tiempo de la pestaña Objetos). No está en MATCH-V5: requiere MATCH-V5
  *timeline* (`/lol/match/v5/matches/{id}/timeline`, eventos
  `ITEM_PURCHASED`), una petición extra por partida y una tabla nueva
  `item_events`.
- **`mvp`** — la corona de la tabla y del gráfico. No existe en la API de Riot:
  se derivaría en SQL una vez haya daño y participación del equipo (p. ej.
  mayor cuota de daño del propio equipo). Hoy la maqueta lo finge con
  `victoria y KDA ≥ 4`.

### Marcador 5v5 (pestaña Equipos)

- **`participants` de los otros nueve jugadores** — aliados y rivales con
  campeón y KDA. De Riot (MATCH-V5 ya los devuelve; hoy `collector.py`
  descarta todo lo que no sea el propio `puuid`). Implica guardar 10 filas por
  partida en `participants` y añadir `team_id`, más `riot_id` de cada jugador.
  Es el cambio más grande de la lista: multiplica por diez el volumen y obliga
  a revisar los índices.

### Identificador y cola de la partida

- **`match_id`** — `/matches` no devuelve ninguna clave de partida: la maqueta
  usa el índice del array. Sin él no se puede pedir el timeline (para
  `build_order`), ni enlazar a una partida, ni cachear su detalle. Ya está en
  `matches`; solo falta exponerlo en la respuesta.
- **`queue_id` legible** — el desplegable pone "Clasificatoria Solo/Duo" fijo.
  `queue_id` está en la tabla `matches` pero tampoco sale por `/matches`:
  exponerlo y mapearlo a nombre (tabla estática o diccionario en el frontend).
- **paginación y filtros (`limit`, `offset`, `champion`, `queue`)** — `/matches`
  devuelve 20 fijas. La tabla ya las agota y el gráfico usa las 10 primeras; en
  cuanto se quiera "ver más" o filtrar por campeón hay que parametrizarlo.

### Nombres y assets (Data Dragon)

No son datos de la API, pero hoy la maqueta los inventa y conviene decidir de
dónde salen.

- **nombre legible del campeón** — `/matches` devuelve la clave interna
  (`Kaisa`, `MonkeyKing`) y la maqueta escribe "Kai'Sa". El mapeo está en
  `cdn/16.17.1/data/es_ES/champion.json`: cargarlo (o resolverlo en la API) en
  vez de mantener una lista a mano.
- **nombres de objetos y hechizos en español** — "Hacha de Kraken",
  "Destello". De `data/es_ES/item.json` y `data/es_ES/summoner.json`; hoy están
  escritos a mano en la maqueta.
- **splash del campeón principal** — el héroe usa
  `cdn/img/champion/splash/{key}_0.jpg`. `DATOS.md` solo documenta el icono
  cuadrado; conviene añadir splash/loading a esa sección.
- **emblema de rango** — la tarjeta de clasificatoria tira de Community Dragon
  (`ranked-mini-crests/{tier}.svg`), otro CDN y sin versionar. Decidir si se
  descarga a `frontend/` junto con los iconos.
- **versión de Data Dragon** — fija a `16.17.1` en el frontend. La API podría
  devolverla (derivada de `game_version`) para no tocar código cada parche.
