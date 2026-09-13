-- Sin esto no se puede saber cuáles de las ~300 compras de una partida son
-- del jugador: item_purchases y skill_levelups identifican por el número
-- dentro de la partida (1-10) y participants solo guardaba el PUUID.
-- El dato ya venía en la respuesta de MATCH-V5, solo faltaba guardarlo.

ALTER TABLE participants
    ADD COLUMN participant_id SMALLINT;
