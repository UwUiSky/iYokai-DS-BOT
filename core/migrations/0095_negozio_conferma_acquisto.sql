-- ECO-069: conferma prima dell'acquisto, per server. Spenta di base: il
-- negozio funziona come prima finché l'admin non la accende.
ALTER TABLE leveling_settings
    ADD COLUMN IF NOT EXISTS shop_confirm BOOLEAN NOT NULL DEFAULT FALSE;
