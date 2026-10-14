-- #141 (D21): registro degli aggiornamenti a caldo del bot, fatti dal proprietario da Discord.
-- Chi, quando, quali file, quale commit, com'è andata. Registro di controllo: si conserva sempre.
CREATE TABLE IF NOT EXISTS hot_patch_log (
    id               SERIAL PRIMARY KEY,
    applied_by       BIGINT NOT NULL,
    source           TEXT NOT NULL CHECK (source IN ('github', 'allegato')),
    commit_sha       TEXT,
    files            JSONB NOT NULL DEFAULT '[]'::jsonb,
    outcome          TEXT NOT NULL CHECK (outcome IN ('ok', 'ripristinato', 'rifiutato')),
    restart_needed   BOOLEAN NOT NULL DEFAULT FALSE,
    detail           TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
