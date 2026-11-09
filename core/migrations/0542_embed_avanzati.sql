-- D69 B4: formato dell'embed pubblicato (classico o componenti V2) e bottoni (link o «mostra tag») da 0 a 24.
ALTER TABLE saved_embeds ADD COLUMN IF NOT EXISTS formato TEXT NOT NULL DEFAULT 'classico'
    CHECK (formato IN ('classico', 'v2'));
CREATE TABLE IF NOT EXISTS embed_bottoni (
    guild_id  BIGINT NOT NULL,
    embed     TEXT NOT NULL,
    posizione INT NOT NULL CHECK (posizione BETWEEN 0 AND 24),
    tipo      TEXT NOT NULL CHECK (tipo IN ('link', 'tag')),
    etichetta TEXT NOT NULL CHECK (char_length(etichetta) BETWEEN 1 AND 80),
    valore    TEXT NOT NULL CHECK (char_length(valore) BETWEEN 1 AND 512),
    PRIMARY KEY (guild_id, embed, posizione),
    FOREIGN KEY (guild_id, embed) REFERENCES saved_embeds (guild_id, name) ON DELETE CASCADE
);
