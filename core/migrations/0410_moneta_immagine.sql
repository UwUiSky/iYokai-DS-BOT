-- D38: immagine della moneta del server. Già ridotta dal bot (PNG 128x128),
-- tetto di 64 KiB. Senza riga si usa la moneta di iYokai.
CREATE TABLE IF NOT EXISTS guild_coin_images (
    guild_id      BIGINT PRIMARY KEY,
    immagine      BYTEA NOT NULL CHECK (octet_length(immagine) <= 65536),
    aggiornato_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
