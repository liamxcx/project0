-- Hasta ahora participants solo guardaba al propio invocador, así que la
-- clave (match_id, puuid) valía. Para guardar a los diez jugadores hace
-- falta otra clave: los otros nueve no tienen PUUID guardado y no se les
-- va a guardar, porque su identidad no hace falta para nada.

-- El número de jugador dentro de la partida (1-10) sí existe siempre, y es
-- único dentro de cada partida. Ese pasa a ser la clave.

-- 1. participant_id se rellenó en V5 pero admitía nulos. Una clave primaria
--    no los admite, así que primero se cierra esa puerta.
ALTER TABLE participants
    ALTER COLUMN participant_id SET NOT NULL;

-- 2. Fuera la clave vieja, dentro la nueva.
ALTER TABLE participants
    DROP CONSTRAINT participants_pkey,
    ADD PRIMARY KEY (match_id, participant_id);

-- 3. El PUUID pasa a ser opcional: lleno para los invocadores seguidos,
--    vacío para los otros nueve. La referencia a summoners se mantiene y
--    sigue protegiendo los que sí lo tengan: en SQL, una clave ajena nula
--    no se comprueba.
ALTER TABLE participants
    ALTER COLUMN puuid DROP NOT NULL;

-- 4. De qué equipo era cada jugador. Riot usa 100 (azul) y 200 (rojo).
--    Sin esto no se puede separar aliados de rivales ni calcular la
--    participación en asesinatos.
ALTER TABLE participants
    ADD COLUMN team_id SMALLINT;

-- 5. Las consultas nuevas van a ser "dame los diez de esta partida" y
--    "dame las partidas de este invocador". La primera la resuelve ya la
--    clave primaria; la segunda perdió su índice al cambiarla, porque el
--    de la clave vieja empezaba por match_id igual.
CREATE INDEX idx_participants_puuid ON participants (puuid, match_id);
