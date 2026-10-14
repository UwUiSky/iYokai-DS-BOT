-- NF-17 (#88): embed salvati dal costruttore, uno per nome in ogni server. Se l'embed è stato
-- pubblicato si ricorda il messaggio, per poterlo modificare dopo.
CREATE TABLE IF NOT EXISTS saved_embeds (
    guild_id   BIGINT NOT NULL,
    name       TEXT NOT NULL CHECK (char_length(name) BETWEEN 1 AND 32),
    data       JSONB NOT NULL,
    channel_id BIGINT,
    message_id BIGINT,
    created_by BIGINT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (guild_id, name)
);
