-- #86 (NF-15), parte rimasta: importi di /daily e /work e tetto di livello per
-- server. Senza valore valgono quelli di prima (200, 20-80, nessun tetto).
-- Nessun dato personale.
ALTER TABLE leveling_settings
    ADD COLUMN IF NOT EXISTS daily_coins INT NOT NULL DEFAULT 200 CHECK (daily_coins BETWEEN 0 AND 10000),
    ADD COLUMN IF NOT EXISTS work_min    INT NOT NULL DEFAULT 20  CHECK (work_min BETWEEN 0 AND 10000),
    ADD COLUMN IF NOT EXISTS work_max    INT NOT NULL DEFAULT 80  CHECK (work_max BETWEEN 0 AND 10000),
    ADD COLUMN IF NOT EXISTS max_level   INT NOT NULL DEFAULT 0   CHECK (max_level BETWEEN 0 AND 1000);
