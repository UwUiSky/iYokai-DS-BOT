-- NF-09 (#80) e M 10.15: comandi personalizzati (tag). Il prefisso per usarli
-- nei messaggi è la colonna guild_config.prefix, finora mai usata.
CREATE TABLE IF NOT EXISTS custom_commands (
    guild_id         BIGINT NOT NULL,
    name             TEXT NOT NULL CHECK (char_length(name) BETWEEN 1 AND 32),
    response         TEXT NOT NULL CHECK (char_length(response) BETWEEN 1 AND 2000),
    use_embed        BOOLEAN NOT NULL DEFAULT FALSE,
    role_id          BIGINT,
    role_action      TEXT NOT NULL DEFAULT 'nessuna' CHECK (role_action IN ('nessuna', 'dai', 'togli', 'alterna')),
    cooldown_seconds INTEGER NOT NULL DEFAULT 0 CHECK (cooldown_seconds BETWEEN 0 AND 3600),
    ping_ruoli       BOOLEAN NOT NULL DEFAULT FALSE,
    uses             INTEGER NOT NULL DEFAULT 0,
    created_by       BIGINT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (guild_id, name)
);
