-- NF-33 (#104): ticket via messaggio privato (ModMail).
-- Una conversazione per utente alla volta (in tutti i server): così un DM
-- arriva sempre a un solo canale dello staff.

CREATE TABLE IF NOT EXISTS modmail_threads (
    id           SERIAL PRIMARY KEY,
    guild_id     BIGINT NOT NULL,
    user_id      BIGINT NOT NULL,
    channel_id   BIGINT NOT NULL UNIQUE,
    status       TEXT NOT NULL DEFAULT 'open',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    closed_at    TIMESTAMPTZ,
    closed_by    BIGINT,
    close_reason TEXT
);

-- Come per i ticket: user_id = 0 è un utente cancellato, non conta come "un utente".
CREATE UNIQUE INDEX IF NOT EXISTS uq_modmail_un_aperto_per_utente
    ON modmail_threads (user_id)
    WHERE status = 'open' AND user_id <> 0;

CREATE INDEX IF NOT EXISTS idx_modmail_threads_guild ON modmail_threads (guild_id, status);

CREATE TABLE IF NOT EXISTS modmail_blocks (
    guild_id   BIGINT NOT NULL,
    user_id    BIGINT NOT NULL,
    blocked_by BIGINT,
    blocked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (guild_id, user_id)
);

-- Categoria dei canali dello staff, per server. Non sta in guild_config.settings:
-- ogni chiave lì deve comparire nello schema di /admin config (cogs/utility).
CREATE TABLE IF NOT EXISTS modmail_config (
    guild_id    BIGINT PRIMARY KEY,
    category_id BIGINT NOT NULL,
    updated_by  BIGINT,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
