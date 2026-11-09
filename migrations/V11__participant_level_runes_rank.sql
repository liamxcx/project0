-- Lo que enseña el detalle de la partida y aún no se guardaba. El nivel y
-- las runas vienen en la misma respuesta de MATCH-V5 que el resto.
-- Admiten NULL porque las partidas ya guardadas no los tienen hasta el
-- siguiente --refetch, y las que Riot ya no sirve no los tendrán nunca.
ALTER TABLE participants
    -- Nivel del campeón al acabar la partida, de 1 a 18
    ADD COLUMN champ_level        SMALLINT,
    -- Los dos árboles de runas, por ejemplo 8000 (Precisión) y 8300 (Inspiración)
    ADD COLUMN primary_style_id   INTEGER,
    ADD COLUMN secondary_style_id INTEGER,
    -- Las seis runas elegidas, en orden: cuatro del árbol principal, la primera
    -- es la principal, y dos del secundario
    ADD COLUMN rune_ids           INTEGER[],
    -- Los tres fragmentos: ofensivo, flexible y defensivo
    ADD COLUMN shard_ids          INTEGER[],
    -- Su Solo/Duo de cuando se guardó la partida, porque Riot no da la que
    -- tenía al jugarla. Como en ranked_snapshots, y NULL si no tiene
    ADD COLUMN tier               TEXT,
    ADD COLUMN division           TEXT,
    ADD COLUMN league_points      INTEGER;
