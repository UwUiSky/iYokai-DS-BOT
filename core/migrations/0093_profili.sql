-- #111 (NF-40): profilo personale per server. Testo di presentazione, badge e
-- sfondo scelti, e gli oggetti comprati con le coin (il catalogo è nel codice).
CREATE TABLE IF NOT EXISTS profile_settings (
    guild_id      BIGINT NOT NULL,
    user_id       BIGINT NOT NULL,
    bio           TEXT   CHECK (bio IS NULL OR char_length(bio) <= 140),
    badge_id      TEXT,
    background_id TEXT,
    PRIMARY KEY (guild_id, user_id)
);

CREATE TABLE IF NOT EXISTS profile_items (
    guild_id    BIGINT      NOT NULL,
    user_id     BIGINT      NOT NULL,
    item_id     TEXT        NOT NULL,
    acquired_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (guild_id, user_id, item_id)
);
