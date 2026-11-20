-- #125 B12 (ECO-060): un oggetto può dare monete o dare/togliere un ruolo quando si usa.
ALTER TABLE shop_items
    ADD COLUMN IF NOT EXISTS azione TEXT NOT NULL DEFAULT 'nessuna',
    ADD COLUMN IF NOT EXISTS azione_valore BIGINT;
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'shop_items_azione_valida') THEN
        ALTER TABLE shop_items ADD CONSTRAINT shop_items_azione_valida
            CHECK (azione IN ('nessuna', 'monete', 'ruolo_dai', 'ruolo_togli')
                   AND (azione = 'nessuna' OR azione_valore > 0));
    END IF;
END $$;
