-- Catalogo #115 (MOD-033, MOD-035): gradini contati in una finestra di giorni, conteggio azzerato dopo la sanzione.
ALTER TABLE automod_escalation_config ADD COLUMN IF NOT EXISTS azzera_dopo_scatto BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE automod_escalation_steps ADD COLUMN IF NOT EXISTS finestra_giorni INTEGER;
ALTER TABLE automod_escalation_steps DROP CONSTRAINT IF EXISTS automod_escalation_steps_finestra_check;
ALTER TABLE automod_escalation_steps ADD CONSTRAINT automod_escalation_steps_finestra_check
    CHECK (finestra_giorni IS NULL OR finestra_giorni BETWEEN 1 AND 90);
CREATE TABLE IF NOT EXISTS automod_violazioni_date (
    guild_id BIGINT NOT NULL,
    user_id  BIGINT NOT NULL,
    quando   TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_automod_violazioni_date ON automod_violazioni_date (guild_id, user_id, quando);
