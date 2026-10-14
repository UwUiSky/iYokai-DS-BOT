-- NF-08 (#79): starboard (bacheca dei messaggi più votati).
CREATE TABLE IF NOT EXISTS starboard_config (
    guild_id   BIGINT PRIMARY KEY,
    channel_id BIGINT NOT NULL,
    threshold  INTEGER NOT NULL DEFAULT 3 CHECK (threshold BETWEEN 1 AND 25),
    emoji      TEXT NOT NULL DEFAULT '⭐',
    enabled    BOOLEAN NOT NULL DEFAULT TRUE,
    allow_nsfw BOOLEAN NOT NULL DEFAULT FALSE,
    self_star  BOOLEAN NOT NULL DEFAULT FALSE
);

-- Una riga per messaggio originale: la chiave primaria garantisce un solo post in bacheca.
CREATE TABLE IF NOT EXISTS starboard_posts (
    source_message_id BIGINT PRIMARY KEY,
    guild_id          BIGINT NOT NULL,
    source_channel_id BIGINT NOT NULL,
    author_id         BIGINT NOT NULL,
    board_message_id  BIGINT,
    stars             INTEGER NOT NULL DEFAULT 0,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_starboard_posts_guild ON starboard_posts (guild_id);
