CREATE TABLE IF NOT EXISTS invocadores (
    puuid       TEXT PRIMARY KEY,
    game_name   TEXT NOT NULL,
    tag_line    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS partidas (
    match_id        TEXT PRIMARY KEY,
    fecha           TIMESTAMPTZ NOT NULL,
    duracion_seg    INTEGER NOT NULL,
    cola_id         INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS participaciones (
    match_id    TEXT REFERENCES partidas(match_id),
    puuid       TEXT REFERENCES invocadores(puuid),
    campeon     TEXT NOT NULL,
    posicion    TEXT,
    kills       INTEGER NOT NULL,
    deaths      INTEGER NOT NULL,
    assists     INTEGER NOT NULL,
    victoria    BOOLEAN NOT NULL,
    PRIMARY KEY (match_id, puuid)
);