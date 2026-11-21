-- Catalogo #128 (UTL-146): canali che non finiscono mai in bacheca (al massimo 25).
ALTER TABLE starboard_config ADD COLUMN IF NOT EXISTS canali_esclusi BIGINT[] NOT NULL DEFAULT '{}';
ALTER TABLE starboard_config DROP CONSTRAINT IF EXISTS starboard_config_esclusi_check;
ALTER TABLE starboard_config ADD CONSTRAINT starboard_config_esclusi_check CHECK (cardinality(canali_esclusi) <= 25);
