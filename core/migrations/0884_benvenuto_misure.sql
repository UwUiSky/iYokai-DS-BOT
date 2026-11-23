-- RUO-005 (D121): immagine di benvenuto con sfondo trasparente e misure a scelta (tetto 2048 px).
ALTER TABLE greetings_config ADD COLUMN IF NOT EXISTS welcome_image_width INTEGER NOT NULL DEFAULT 1024;
ALTER TABLE greetings_config ADD COLUMN IF NOT EXISTS welcome_image_height INTEGER NOT NULL DEFAULT 400;
ALTER TABLE greetings_config ADD COLUMN IF NOT EXISTS welcome_image_transparent BOOLEAN NOT NULL DEFAULT FALSE;
