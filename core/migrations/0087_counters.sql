-- NF-16 (#87): canali contatore (membri, online, boost, obiettivo).
CREATE TABLE IF NOT EXISTS counters (
    id         SERIAL PRIMARY KEY,
    guild_id   BIGINT NOT NULL,
    channel_id BIGINT NOT NULL,
    kind       TEXT NOT NULL CHECK (kind IN ('members', 'online', 'boosts', 'goal')),
    label      TEXT NOT NULL CHECK (char_length(label) BETWEEN 1 AND 100),
    target     INTEGER CHECK (target IS NULL OR target > 0),
    last_value INTEGER,
    created_by BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (guild_id, channel_id)
);
