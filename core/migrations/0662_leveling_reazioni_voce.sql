-- #124 B5 (LIV-008, 009, 059, 060): XP per le reazioni messe e ricevute (spento di base), conteggio delle
-- reazioni per la classifica, minuti totali in vocale per la classifica vocale.
ALTER TABLE leveling_settings
    ADD COLUMN IF NOT EXISTS xp_reazione_messa INTEGER NOT NULL DEFAULT 0
        CHECK (xp_reazione_messa BETWEEN 0 AND 20),
    ADD COLUMN IF NOT EXISTS xp_reazione_ricevuta INTEGER NOT NULL DEFAULT 0
        CHECK (xp_reazione_ricevuta BETWEEN 0 AND 20),
    ADD COLUMN IF NOT EXISTS reazioni_attesa INTEGER NOT NULL DEFAULT 300
        CHECK (reazioni_attesa BETWEEN 60 AND 3600);

ALTER TABLE leveling_totals
    ADD COLUMN IF NOT EXISTS voice_minutes_total BIGINT NOT NULL DEFAULT 0;

CREATE TABLE IF NOT EXISTS leveling_reazioni (
    guild_id        BIGINT      NOT NULL,
    user_id         BIGINT      NOT NULL,
    messe           BIGINT      NOT NULL DEFAULT 0,
    ricevute        BIGINT      NOT NULL DEFAULT 0,
    ultima_messa    TIMESTAMPTZ,
    ultima_ricevuta TIMESTAMPTZ,
    messe_oggi      INTEGER     NOT NULL DEFAULT 0,
    ricevute_oggi   INTEGER     NOT NULL DEFAULT 0,
    giorno_messa    DATE,
    giorno_ricevuta DATE,
    PRIMARY KEY (guild_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_leveling_reazioni_messe ON leveling_reazioni (guild_id, messe DESC);
CREATE INDEX IF NOT EXISTS idx_leveling_reazioni_ricevute ON leveling_reazioni (guild_id, ricevute DESC);
