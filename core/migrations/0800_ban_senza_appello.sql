-- Catalogo #115 (MOD-008): un ban, un tempban o un timeout segnato «senza appello»: niente bottone, appello rifiutato.
ALTER TABLE moderation_cases ADD COLUMN IF NOT EXISTS senza_appello BOOLEAN NOT NULL DEFAULT FALSE;
