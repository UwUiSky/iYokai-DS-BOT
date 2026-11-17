-- #124 B6 (LIV-051, 054, 055, 056): colore di testo e bordi e velo sopra lo sfondo (per utente),
-- sfondo e colore predefiniti del server per tutte le card.
ALTER TABLE rank_card_prefs
    ADD COLUMN IF NOT EXISTS colore_testo TEXT CHECK (colore_testo ~ '^#[0-9A-F]{6}$'),
    ADD COLUMN IF NOT EXISTS velo SMALLINT CHECK (velo BETWEEN 0 AND 100);

ALTER TABLE leveling_settings
    ADD COLUMN IF NOT EXISTS card_colore TEXT NOT NULL DEFAULT ''
        CHECK (card_colore = '' OR card_colore = 'auto' OR card_colore ~ '^#[0-9A-F]{6}$');

CREATE TABLE IF NOT EXISTS guild_card_sfondi (
    guild_id      BIGINT PRIMARY KEY,
    immagine      BYTEA NOT NULL CHECK (octet_length(immagine) <= 262144),
    aggiornato_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
