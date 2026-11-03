-- Icono y nivel de la cuenta, de SUMMONER-V4. El collector los sobrescribe en
-- cada vuelta, porque solo interesa el valor actual y no su historial.
-- Admiten NULL porque las filas que ya existen no los tienen hasta la
-- siguiente vuelta del collector.
ALTER TABLE summoners
    ADD COLUMN profile_icon_id INTEGER,
    ADD COLUMN summoner_level  INTEGER;
