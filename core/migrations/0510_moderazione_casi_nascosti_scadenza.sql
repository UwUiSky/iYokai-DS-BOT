-- Casi di moderazione: nascosti (MOD-045), scadenza dei casi AutoMod (MOD-048), origine del caso.
-- `origine`: 'manuale' (comando dello staff), 'automod' (sanzione automatica), 'esterno' (azione fatta fuori dal bot).
ALTER TABLE moderation_cases ADD COLUMN IF NOT EXISTS hidden BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE moderation_cases ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ;
ALTER TABLE moderation_cases ADD COLUMN IF NOT EXISTS origine TEXT NOT NULL DEFAULT 'manuale';
CREATE INDEX IF NOT EXISTS idx_moderation_cases_scadenza
    ON moderation_cases (expires_at) WHERE active AND expires_at IS NOT NULL;
