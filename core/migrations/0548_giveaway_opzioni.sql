-- D69 B9-B10: ruolo escluso, ruolo premio, immagine e colore per giveaway e modello; vincitori sugli iscritti
-- (ripescaggio: chi è stato sostituito non si estrae più); opzioni per server (aspetto, messaggi, log, ruoli esclusi).
ALTER TABLE giveaways
    ADD COLUMN IF NOT EXISTS ruolo_escluso BIGINT,
    ADD COLUMN IF NOT EXISTS ruolo_premio  BIGINT,
    ADD COLUMN IF NOT EXISTS immagine_url  TEXT CHECK (immagine_url IS NULL OR char_length(immagine_url) <= 1000),
    ADD COLUMN IF NOT EXISTS colore        INT CHECK (colore IS NULL OR colore BETWEEN 0 AND 16777215);

ALTER TABLE giveaway_templates
    ADD COLUMN IF NOT EXISTS ruolo_escluso BIGINT,
    ADD COLUMN IF NOT EXISTS ruolo_premio  BIGINT,
    ADD COLUMN IF NOT EXISTS immagine_url  TEXT CHECK (immagine_url IS NULL OR char_length(immagine_url) <= 1000);

ALTER TABLE giveaway_entries
    ADD COLUMN IF NOT EXISTS vincitore BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS scartato  BOOLEAN NOT NULL DEFAULT FALSE;

CREATE INDEX IF NOT EXISTS idx_giveaways_messaggio ON giveaways (message_id) WHERE message_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS giveaway_opzioni (
    guild_id       BIGINT PRIMARY KEY,
    colore         INT CHECK (colore IS NULL OR colore BETWEEN 0 AND 16777215),
    bottone_emoji  TEXT CHECK (bottone_emoji IS NULL OR char_length(bottone_emoji) <= 64),
    bottone_testo  TEXT CHECK (bottone_testo IS NULL OR char_length(bottone_testo) <= 80),
    msg_conferma   TEXT CHECK (msg_conferma IS NULL OR char_length(msg_conferma) <= 500),
    msg_dm         TEXT CHECK (msg_dm IS NULL OR char_length(msg_dm) <= 1000),
    canale_log     BIGINT,
    ruoli_esclusi  BIGINT[] NOT NULL DEFAULT '{}' CHECK (cardinality(ruoli_esclusi) <= 25)
);
