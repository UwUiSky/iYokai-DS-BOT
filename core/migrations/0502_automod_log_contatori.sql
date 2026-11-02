-- D63: ogni violazione ricorda la regola e il contatore a cui appartiene (X violazioni in Y minuti, azzera).
ALTER TABLE automod_action_log ADD COLUMN IF NOT EXISTS regola_id BIGINT;
ALTER TABLE automod_action_log ADD COLUMN IF NOT EXISTS contatore TEXT;
CREATE INDEX IF NOT EXISTS idx_automod_action_log_contatore
    ON automod_action_log (guild_id, user_id, contatore, created_at DESC) WHERE contatore IS NOT NULL;
