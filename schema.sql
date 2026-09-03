CREATE TABLE IF NOT EXISTS summoners (
    puuid       TEXT PRIMARY KEY,
    game_name   TEXT NOT NULL,
    tag_line    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS matches (
    match_id            TEXT PRIMARY KEY,
    played_at           TIMESTAMPTZ NOT NULL,
    duration_seconds    INTEGER NOT NULL,
    queue_id            INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS participants (
    match_id    TEXT REFERENCES matches(match_id),
    puuid       TEXT REFERENCES summoners(puuid),
    champion    TEXT NOT NULL,
    position    TEXT,
    kills       INTEGER NOT NULL,
    deaths      INTEGER NOT NULL,
    assists     INTEGER NOT NULL,
    win         BOOLEAN NOT NULL,
    PRIMARY KEY (match_id, puuid)
);
