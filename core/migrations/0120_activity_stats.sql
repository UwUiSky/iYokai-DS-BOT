-- NF-25 (#96): statistiche di attività. Solo aggregati per giorno (mai un messaggio):
-- niente righe per messaggio, la tabella cresce con (giorni x canali) e (giorni x membri attivi).
-- Pulizia dopo 90 giorni (core/data_registry.py, Scadenza).
CREATE TABLE IF NOT EXISTS activity_channel_daily (
    guild_id      BIGINT NOT NULL,
    day           DATE   NOT NULL,
    channel_id    BIGINT NOT NULL,
    messages      INTEGER NOT NULL DEFAULT 0,
    voice_seconds INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (guild_id, day, channel_id)
);
CREATE TABLE IF NOT EXISTS activity_member_daily (
    guild_id      BIGINT NOT NULL,
    day           DATE   NOT NULL,
    user_id       BIGINT NOT NULL,
    messages      INTEGER NOT NULL DEFAULT 0,
    voice_seconds INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (guild_id, day, user_id)
);
CREATE INDEX IF NOT EXISTS idx_activity_member_user ON activity_member_daily (guild_id, user_id, day);
CREATE TABLE IF NOT EXISTS activity_hour_daily (
    guild_id      BIGINT NOT NULL,
    day           DATE   NOT NULL,
    hour          SMALLINT NOT NULL CHECK (hour BETWEEN 0 AND 23),
    messages      INTEGER NOT NULL DEFAULT 0,
    voice_seconds INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (guild_id, day, hour)
);
CREATE TABLE IF NOT EXISTS activity_settings (
    guild_id         BIGINT PRIMARY KEY,
    ignored_channels BIGINT[] NOT NULL DEFAULT '{}',
    ignored_roles    BIGINT[] NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS activity_roles (
    id                SERIAL PRIMARY KEY,
    guild_id          BIGINT NOT NULL,
    role_id           BIGINT NOT NULL,
    metric            TEXT NOT NULL CHECK (metric IN ('messages', 'voice_minutes')),
    threshold         INTEGER NOT NULL CHECK (threshold > 0),
    period_days       SMALLINT NOT NULL CHECK (period_days BETWEEN 1 AND 90),
    remove_when_below BOOLEAN NOT NULL DEFAULT TRUE,
    UNIQUE (guild_id, role_id)
);
