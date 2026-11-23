-- r1doc (LIV-013): XP da messaggi e XP da vocale tenuti a parte, per le due classifiche e i due livelli.
-- Gli XP di prima non si dividono (non si sa da dove venivano): le due colonne partono da zero.
ALTER TABLE leveling_totals
    ADD COLUMN IF NOT EXISTS xp_testo  BIGINT NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS xp_vocale BIGINT NOT NULL DEFAULT 0;

CREATE INDEX IF NOT EXISTS idx_leveling_totals_guild_xp_testo
    ON leveling_totals (guild_id, xp_testo DESC) WHERE xp_testo > 0;
CREATE INDEX IF NOT EXISTS idx_leveling_totals_guild_xp_vocale
    ON leveling_totals (guild_id, xp_vocale DESC) WHERE xp_vocale > 0;
