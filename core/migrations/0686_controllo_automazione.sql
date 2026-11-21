-- #125 B16 (ECO-158): controllo anti-automazione nei comandi di guadagno (probabilità in millesimi, 0 = spento).
ALTER TABLE leveling_settings ADD COLUMN IF NOT EXISTS controllo_per_mille INTEGER NOT NULL DEFAULT 0;
