-- 8.17: vista dei log su un forum, un post per canale o per caso.
CREATE TABLE IF NOT EXISTS log_forum_viste (
    guild_id   BIGINT NOT NULL,
    dimensione TEXT NOT NULL CHECK (dimensione IN ('canali', 'casi')),
    forum_id   BIGINT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (guild_id, dimensione)
);

CREATE TABLE IF NOT EXISTS log_forum_post (
    guild_id   BIGINT NOT NULL,
    dimensione TEXT NOT NULL CHECK (dimensione IN ('canali', 'casi')),
    chiave     BIGINT NOT NULL,
    thread_id  BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (guild_id, dimensione, chiave)
);
