-- #91 (NF-20): sessioni di accesso al pannello web. Si salva solo l'impronta
-- (SHA-256) del token del cookie, mai il token. Nessun token OAuth di Discord.
CREATE TABLE IF NOT EXISTS web_panel_sessions (
    token_hash   TEXT PRIMARY KEY,
    user_id      BIGINT NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at   TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_web_panel_sessions_user ON web_panel_sessions (user_id);
CREATE INDEX IF NOT EXISTS idx_web_panel_sessions_expires ON web_panel_sessions (expires_at);
