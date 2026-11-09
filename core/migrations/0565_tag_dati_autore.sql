-- D69 B26: chi ha scritto la chiave di {dati:set}, per il tetto per autore (le righe di prima restano senza autore).
ALTER TABLE tag_dati ADD COLUMN IF NOT EXISTS autore BIGINT;
CREATE INDEX IF NOT EXISTS idx_tag_dati_autore ON tag_dati (guild_id, autore);
