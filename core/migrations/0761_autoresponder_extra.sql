-- Catalogo #128 (UTL-060, 062, 064, 065, 066): modo «finisce con», maiuscole che contano, utenti, canali e ruoli esclusi
-- (al massimo 10 per elenco).
ALTER TABLE autoresponders DROP CONSTRAINT IF EXISTS autoresponders_match_mode_check;
ALTER TABLE autoresponders ADD CONSTRAINT autoresponders_match_mode_check
    CHECK (match_mode IN ('esatta', 'parziale', 'inizia', 'finisce', 'regex'));
ALTER TABLE autoresponders
    ADD COLUMN IF NOT EXISTS maiuscole      BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS canali_esclusi BIGINT[] NOT NULL DEFAULT '{}',
    ADD COLUMN IF NOT EXISTS utenti_esclusi BIGINT[] NOT NULL DEFAULT '{}',
    ADD COLUMN IF NOT EXISTS ruoli_esclusi  BIGINT[] NOT NULL DEFAULT '{}';
ALTER TABLE autoresponders DROP CONSTRAINT IF EXISTS autoresponders_esclusi_check;
ALTER TABLE autoresponders ADD CONSTRAINT autoresponders_esclusi_check
    CHECK (cardinality(canali_esclusi) <= 10 AND cardinality(utenti_esclusi) <= 10 AND cardinality(ruoli_esclusi) <= 10);
