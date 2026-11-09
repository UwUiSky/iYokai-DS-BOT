-- D69 B8: bacheca bloccata (solo il bot scrive) e canale «sorgente» da cui ogni messaggio va in bacheca.
ALTER TABLE starboard_config ADD COLUMN IF NOT EXISTS blocca BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE starboard_config ADD COLUMN IF NOT EXISTS canale_auto BIGINT;
