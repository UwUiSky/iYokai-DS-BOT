-- NF-11 (#82): immagine di benvenuto. La tabella greetings_config nasce nel codice di base
-- (greetings_repo.run_migrations), che gira prima delle migrazioni numerate.
ALTER TABLE greetings_config ADD COLUMN IF NOT EXISTS welcome_image_enabled        BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE greetings_config ADD COLUMN IF NOT EXISTS welcome_image_template       TEXT NOT NULL DEFAULT 'scuro';
ALTER TABLE greetings_config ADD COLUMN IF NOT EXISTS welcome_image_shape          TEXT NOT NULL DEFAULT 'tondo';
ALTER TABLE greetings_config ADD COLUMN IF NOT EXISTS welcome_image_color          TEXT NOT NULL DEFAULT '#FFFFFF';
ALTER TABLE greetings_config ADD COLUMN IF NOT EXISTS welcome_image_title          TEXT NOT NULL DEFAULT 'Benvenuto';
ALTER TABLE greetings_config ADD COLUMN IF NOT EXISTS welcome_image_has_background BOOLEAN NOT NULL DEFAULT FALSE;

-- Lo sfondo sta in una tabella a parte: get_config legge "tutta la riga" a ogni ingresso
-- e uno sfondo da qualche centinaio di KB non deve andare con lei.
CREATE TABLE IF NOT EXISTS greetings_background (
    guild_id   BIGINT PRIMARY KEY,
    image      BYTEA NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
