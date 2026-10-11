-- #148: token OAuth2 dell'admin che ha autorizzato il bot a scrivere i permessi dei
-- comandi (scope applications.commands.permissions.update). Un token per server,
-- sempre cifrato (core/oauth_crypto.py); non si stampa né si esporta mai.
CREATE TABLE IF NOT EXISTS command_permission_tokens (
    guild_id                BIGINT PRIMARY KEY,
    user_id                 BIGINT NOT NULL,
    encrypted_access_token  TEXT NOT NULL,
    encrypted_refresh_token TEXT NOT NULL,
    expires_at              TIMESTAMPTZ NOT NULL,
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_command_permission_tokens_utente ON command_permission_tokens (user_id);
