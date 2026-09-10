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

### Cabecera del jugador

- **`tier`, `division`, `league_points`** — tarjeta de clasificatoria: "Master
  700 LP" y la barra de progreso hacia el siguiente escalón. De Riot
  (LEAGUE-V4, `/lol/league/v4/entries/by-puuid/{puuid}`); tabla nueva
  `ranked_entries` o columnas en `summoners`.
- **`gm_cutoff_lp`** — el corte de Gran Maestro de la región, para el "faltan
  1.100 LP" de la barra. De Riot (LEAGUE-V4, `challengerleagues`/
  `grandmasterleagues`); solo aplica a Master+.
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

### Cola y filtros

- **`queue_id` legible** — el desplegable pone "Clasificatoria Solo/Duo" fijo.
  `queue_id` ya está en `matches`, solo falta el mapeo a nombre (tabla estática
  o diccionario en el frontend).

