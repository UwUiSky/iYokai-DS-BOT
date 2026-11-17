-- #126 (r4mus): MUS-042 coda che si ritrova dopo un riavvio (una per canale vocale).
CREATE TABLE IF NOT EXISTS music_saved_queues (
    guild_id    BIGINT NOT NULL,
    channel_id  BIGINT NOT NULL,
    tracks      JSONB NOT NULL DEFAULT '[]'::jsonb,
    saved_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (guild_id, channel_id)
);
