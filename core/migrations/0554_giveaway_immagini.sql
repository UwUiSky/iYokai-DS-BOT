-- D69 B9: l'immagine del giveaway si conserva (copia ricodificata dalla pipeline) invece dell'URL dell'allegato,
-- che scade sul CDN di Discord. Il giveaway e il modello puntano alla copia.
CREATE TABLE IF NOT EXISTS giveaway_immagini (
    id         SERIAL PRIMARY KEY,
    guild_id   BIGINT NOT NULL,
    sha256     TEXT NOT NULL,
    dati       BYTEA NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (guild_id, sha256)
);

ALTER TABLE giveaways          ADD COLUMN IF NOT EXISTS immagine_id INT;
ALTER TABLE giveaway_templates ADD COLUMN IF NOT EXISTS immagine_id INT;
ALTER TABLE giveaways          DROP COLUMN IF EXISTS immagine_url;
ALTER TABLE giveaway_templates DROP COLUMN IF EXISTS immagine_url;
