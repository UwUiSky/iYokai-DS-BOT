-- Catalogo #123 (RUO-001, 014, 015): nome dell'embed salvato per benvenuto, DM e addio ('' = nessuno).
ALTER TABLE greetings_config ADD COLUMN IF NOT EXISTS welcome_embed TEXT NOT NULL DEFAULT '';
ALTER TABLE greetings_config ADD COLUMN IF NOT EXISTS dm_embed TEXT NOT NULL DEFAULT '';
ALTER TABLE greetings_config ADD COLUMN IF NOT EXISTS goodbye_embed TEXT NOT NULL DEFAULT '';
