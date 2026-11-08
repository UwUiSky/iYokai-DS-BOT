-- Slowmode lungo gestito dal bot (MOD-099): oltre le 6 ore di Discord, fino a 7 giorni.
-- `ultimi` tiene l'ultimo messaggio di ogni utente nei canali con slowmode lungo; si pulisce da solo (data registry).
CREATE TABLE IF NOT EXISTS moderation_slowmode_lungo (
    guild_id   BIGINT NOT NULL,
    channel_id BIGINT NOT NULL,
    secondi    INTEGER NOT NULL,
    PRIMARY KEY (guild_id, channel_id)
);
CREATE TABLE IF NOT EXISTS moderation_slowmode_ultimi (
    guild_id   BIGINT      NOT NULL,
    channel_id BIGINT      NOT NULL,
    user_id    BIGINT      NOT NULL,
    ultimo_at  TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (guild_id, channel_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_moderation_slowmode_ultimi_at ON moderation_slowmode_ultimi (ultimo_at);
