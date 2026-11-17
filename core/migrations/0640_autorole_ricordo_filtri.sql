-- Catalogo #123 (RUO-040, 041): quali ruoli si ricordano e quali mai.
-- remember_allowed: se non è vuoto, si ricordano solo questi; remember_excluded: mai questi.
ALTER TABLE autorole_config ADD COLUMN IF NOT EXISTS remember_allowed BIGINT[] NOT NULL DEFAULT '{}';
ALTER TABLE autorole_config ADD COLUMN IF NOT EXISTS remember_excluded BIGINT[] NOT NULL DEFAULT '{}';
