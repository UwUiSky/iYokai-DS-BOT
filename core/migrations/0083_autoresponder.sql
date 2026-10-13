-- NF-10 (#81): risposte automatiche a parole o frasi scelte dal server.
CREATE TABLE IF NOT EXISTS autoresponders (
    id          SERIAL PRIMARY KEY,
    guild_id    BIGINT NOT NULL,
    trigger     TEXT NOT NULL CHECK (char_length(trigger) BETWEEN 1 AND 100),
    match_mode  TEXT NOT NULL DEFAULT 'parziale' CHECK (match_mode IN ('esatta', 'parziale')),
    response    TEXT NOT NULL CHECK (char_length(response) BETWEEN 1 AND 2000),
    channel_id  BIGINT,
    role_id     BIGINT,
    ping_ruoli  BOOLEAN NOT NULL DEFAULT FALSE,
    created_by  BIGINT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_autoresponders_trigger ON autoresponders (guild_id, lower(trigger));
