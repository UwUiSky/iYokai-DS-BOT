-- RUO-013, 017, 023, 025 (#123): DM con testo suo, varianti a caso, reazioni sul messaggio di benvenuto.
ALTER TABLE greetings_config ADD COLUMN IF NOT EXISTS welcome_dm_message TEXT NOT NULL DEFAULT '';
ALTER TABLE greetings_config ADD COLUMN IF NOT EXISTS welcome_variants   TEXT[] NOT NULL DEFAULT '{}';
ALTER TABLE greetings_config ADD COLUMN IF NOT EXISTS welcome_reactions  TEXT[] NOT NULL DEFAULT '{}';
