-- NF-12 (#83) e NF-40 (#111): sfondo con un'immagine propria per rank
-- card e profilo. L'immagine è già ridotta e ricompressa dal bot
-- (JPEG 800x360), quindi resta piccola: tetto di 256 KiB.
CREATE TABLE IF NOT EXISTS rank_card_sfondi (
    user_id       BIGINT PRIMARY KEY,
    immagine      BYTEA NOT NULL CHECK (octet_length(immagine) <= 262144),
    aggiornato_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- Un server può non mostrare gli sfondi con immagine (LIV-057: al posto
-- della segnalazione di una card non adatta, lo staff li spegne).
ALTER TABLE leveling_settings ADD COLUMN IF NOT EXISTS card_images BOOLEAN NOT NULL DEFAULT TRUE;
