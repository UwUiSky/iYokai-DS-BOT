-- ECO-001 (nome della moneta) ed ECO-015 (tassa e tetto sui trasferimenti, /level pay).
-- Senza valori tutto resta com'era: moneta «coin», nessuna tassa, nessun tetto.
ALTER TABLE leveling_settings
    ADD COLUMN IF NOT EXISTS currency_name TEXT NOT NULL DEFAULT 'coin'
        CHECK (char_length(currency_name) BETWEEN 1 AND 20),
    ADD COLUMN IF NOT EXISTS pay_tax_pct  INT NOT NULL DEFAULT 0
        CHECK (pay_tax_pct BETWEEN 0 AND 50),
    ADD COLUMN IF NOT EXISTS pay_max      INT NOT NULL DEFAULT 0
        CHECK (pay_max BETWEEN 0 AND 1000000);
