-- Tu clasificatoria de Solo/Duo según LEAGUE-V4. El collector añade una fila en
-- cada vuelta y no sobrescribe la anterior, para tener el historial de LP.
CREATE TABLE IF NOT EXISTS ranked_snapshots (
    puuid           TEXT        NOT NULL REFERENCES summoners(puuid),
    taken_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- IRON ... CHALLENGER, tal como lo da Riot
    tier            TEXT        NOT NULL,
    -- I ... IV. En Master, Grandmaster y Challenger Riot devuelve siempre I
    division        TEXT        NOT NULL,
    league_points   INTEGER     NOT NULL,
    wins            INTEGER     NOT NULL,
    losses          INTEGER     NOT NULL,
    -- LP del último jugador del escalón siguiente, en Master y Grandmaster.
    -- En el resto de rangos no hay corte, porque se sube al llegar a 100 LP.
    next_cutoff_lp  INTEGER,
    -- La API siempre pide la foto más reciente de un invocador, y esta clave
    -- ya le sirve de índice
    PRIMARY KEY (puuid, taken_at)
);
