-- Borrar una partida obligaba a vaciar antes a mano las tres tablas que la
-- referencian. Con ON DELETE CASCADE, Postgres se encarga: al borrar la
-- fila de matches desaparecen sus participantes, sus compras y sus subidas
-- de habilidad.

-- Una clave ajena no se puede modificar, hay que quitarla y volver a
-- crearla. Cada par va en un solo ALTER TABLE para que sea una sola
-- operación y la tabla no se quede un instante sin la restricción.

ALTER TABLE participants
    DROP CONSTRAINT participants_match_id_fkey,
    ADD CONSTRAINT participants_match_id_fkey
        FOREIGN KEY (match_id) REFERENCES matches(match_id) ON DELETE CASCADE;

ALTER TABLE item_purchases
    DROP CONSTRAINT item_purchases_match_id_fkey,
    ADD CONSTRAINT item_purchases_match_id_fkey
        FOREIGN KEY (match_id) REFERENCES matches(match_id) ON DELETE CASCADE;

ALTER TABLE skill_levelups
    DROP CONSTRAINT skill_levelups_match_id_fkey,
    ADD CONSTRAINT skill_levelups_match_id_fkey
        FOREIGN KEY (match_id) REFERENCES matches(match_id) ON DELETE CASCADE;

-- participants_puuid_fkey se queda como está. Borrar un invocador de la
-- lista de seguidos no debe llevarse sus participaciones por delante: esas
-- partidas siguen existiendo y el resto de sus datos sigue sirviendo.
