-- ECO-015: anche il minimo per ogni /level pay (0 = nessun minimo).
ALTER TABLE leveling_settings
    ADD COLUMN IF NOT EXISTS pay_min INT NOT NULL DEFAULT 0
        CHECK (pay_min BETWEEN 0 AND 1000000);
