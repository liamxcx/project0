-- Todo esto ya viene en la respuesta de MATCH-V5 que el collector descarga,
-- así que no cuesta ni una petición más a Riot.
-- Se dejan NULL a propósito en las partidas guardadas antes de este cambio:
-- NULL es "no lo sé", y un 0 diría "jugó y no hizo nada", que es falso.

ALTER TABLE participants
    -- totalDamageDealtToChampions y totalDamageTaken
    ADD COLUMN damage_to_champions INTEGER,
    ADD COLUMN damage_taken        INTEGER,

    -- goldEarned
    ADD COLUMN gold_earned         INTEGER,

    -- El CS es la suma de los dos: súbditos de calle y monstruos de jungla.
    -- Se guardan por separado porque Riot los da por separado; sumar es cosa
    -- de la consulta.
    ADD COLUMN minions_killed         INTEGER,
    ADD COLUMN neutral_minions_killed INTEGER,

    -- visionScore y wardsPlaced
    ADD COLUMN vision_score       INTEGER,
    ADD COLUMN wards_placed       INTEGER,

    -- Build final. Riot devuelve item0..item6 con el id del objeto, o 0 si
    -- el hueco está vacío. El item6 es el trinket.
    ADD COLUMN item0 INTEGER,
    ADD COLUMN item1 INTEGER,
    ADD COLUMN item2 INTEGER,
    ADD COLUMN item3 INTEGER,
    ADD COLUMN item4 INTEGER,
    ADD COLUMN item5 INTEGER,
    ADD COLUMN item6 INTEGER,

    -- Hechizos de invocador (flash, destello, etc.), por id
    ADD COLUMN summoner1_id INTEGER,
    ADD COLUMN summoner2_id INTEGER;
