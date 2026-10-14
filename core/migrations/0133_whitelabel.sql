-- NF-38 (#109): bot con marchio proprio. Un server premium collega un'applicazione Discord sua (nome e avatar suoi).
-- Il token è cifrato a riposo (OAUTH_ENCRYPTION_KEY) e si cancella con il server (core/data_registry.py).
CREATE TABLE IF NOT EXISTS whitelabel_bots (
    guild_id        BIGINT PRIMARY KEY,
    encrypted_token TEXT NOT NULL,
    bot_account_id     BIGINT NOT NULL UNIQUE,
    application_id  BIGINT NOT NULL,
    bot_name        TEXT NOT NULL,
    status_text     TEXT,
    enabled         BOOLEAN NOT NULL DEFAULT TRUE,
    last_state      TEXT NOT NULL DEFAULT 'fermo',
    last_error      TEXT,
    created_by      BIGINT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
