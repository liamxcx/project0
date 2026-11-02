-- Nota de 0 a 10 de cada jugador y los sellos de la partida: MVP para el
-- mejor del equipo que gana y BASTION para el mejor del que pierde.
-- Es una vista y no una tabla, así que se calcula al leerla y siempre sale
-- de los datos que haya en participants en ese momento.

CREATE VIEW participant_scores AS
WITH stats AS (
    SELECT match_id,
           participant_id,
           team_id,
           win,
           (kills + assists)::numeric / GREATEST(deaths, 1) AS kda,
           -- Con 0 asesinatos en el equipo la división daría NULL, y se deja en 0
           COALESCE(
               (kills + assists)::numeric
                   / NULLIF(SUM(kills) OVER (PARTITION BY match_id, team_id), 0),
               0
           ) AS kill_participation,
           damage_to_champions::numeric AS damage,
           vision_score::numeric AS vision,
           COUNT(*) OVER (PARTITION BY match_id) AS players
    FROM participants
),
scores AS (
    SELECT match_id,
           participant_id,
           team_id,
           win,
           -- Cada estadística se divide por la mejor de los diez, para que una
           -- partida larga no dé notas más altas que una corta
           CASE WHEN players = 10 THEN
               ROUND(10 * (
                     kda / NULLIF(MAX(kda) OVER match, 0)
                   + kill_participation / NULLIF(MAX(kill_participation) OVER match, 0)
                   + damage / NULLIF(MAX(damage) OVER match, 0)
                   + vision / NULLIF(MAX(vision) OVER match, 0)
               ) / 4, 1)
           END AS score
    FROM stats
    WINDOW match AS (PARTITION BY match_id)
)
SELECT match_id,
       participant_id,
       score,
       -- Las partidas guardadas antes de tener el daño o los diez jugadores no
       -- tienen nota, así que tampoco se les pone sello
       CASE
           WHEN score IS NULL THEN NULL
           WHEN ROW_NUMBER() OVER (
               PARTITION BY match_id, team_id
               ORDER BY score DESC NULLS LAST, participant_id
           ) > 1 THEN NULL
           WHEN win THEN 'MVP'
           ELSE 'BASTION'
       END AS badge
FROM scores;
