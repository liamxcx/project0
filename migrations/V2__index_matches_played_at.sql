-- /matches ordena por fecha descendente y se queda con las últimas.
-- Sin índice, Postgres recorre y ordena la tabla entera cada vez.
CREATE INDEX idx_matches_played_at ON matches (played_at DESC);
