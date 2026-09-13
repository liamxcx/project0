-- Eventos del endpoint timeline de MATCH-V5. Son listas: una partida tiene
-- unas 300 compras y 180 subidas de habilidad de los diez jugadores, así que
-- no caben como columnas de participants y necesitan tabla propia.

-- Los jugadores se identifican por su número dentro de la partida (1-10),
-- no por PUUID: para el análisis de builds basta, y así no se guarda la
-- identidad de nadie más.

CREATE TABLE IF NOT EXISTS item_purchases (
    -- Clave propia porque el resto no distingue: comprar dos pociones a la
    -- vez genera dos eventos idénticos, mismo objeto y mismo milisegundo.
    id             BIGSERIAL PRIMARY KEY,
    match_id       TEXT     NOT NULL REFERENCES matches(match_id),
    participant_id SMALLINT NOT NULL,
    item_id        INTEGER  NOT NULL,
    -- Milisegundos desde el inicio de la partida, no una fecha
    timestamp_ms   INTEGER  NOT NULL
);

CREATE TABLE IF NOT EXISTS skill_levelups (
    id             BIGSERIAL PRIMARY KEY,
    match_id       TEXT     NOT NULL REFERENCES matches(match_id),
    participant_id SMALLINT NOT NULL,
    -- 1=Q, 2=W, 3=E, 4=R
    skill_slot     SMALLINT NOT NULL,
    -- NORMAL casi siempre; EVOLVE en campeones que evolucionan habilidades
    level_up_type  TEXT     NOT NULL,
    timestamp_ms   INTEGER  NOT NULL
);

-- Las consultas siempre parten de una partida y un jugador: "dame las compras
-- de esta partida en orden". Sin índice, Postgres recorrería la tabla entera.
CREATE INDEX idx_item_purchases_match ON item_purchases (match_id, participant_id, timestamp_ms);
CREATE INDEX idx_skill_levelups_match ON skill_levelups (match_id, participant_id, timestamp_ms);
