-- #129 (ALR-013): eventi Discord creati dal calendario Twitch. Interruttore per avviso e registro dei segmenti già fatti.
ALTER TABLE alert_options ADD COLUMN IF NOT EXISTS schedule_events BOOLEAN NOT NULL DEFAULT false;

CREATE TABLE IF NOT EXISTS twitch_eventi_creati (
    guild_id   BIGINT NOT NULL,
    sub_id     INTEGER NOT NULL,
    segment_id TEXT NOT NULL,
    event_id   BIGINT NOT NULL,
    start_time TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (guild_id, sub_id, segment_id)
);
