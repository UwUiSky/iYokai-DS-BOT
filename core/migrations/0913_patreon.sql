-- CFG-036: Patreon. Collegamento dell'account Patreon a quello Discord (token cifrati), stato dei sostenitori
-- ricevuto dal webhook, eventi già visti (idempotenza), stati OAuth monouso e associazione livelli Patreon -> livelli del bot.
CREATE TABLE IF NOT EXISTS patreon_collegamenti (
    discord_user_id BIGINT PRIMARY KEY,
    patreon_id TEXT NOT NULL UNIQUE,
    token_cifrato   TEXT NOT NULL,
    refresh_cifrato TEXT,
    creato_il       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS patreon_membri (
    patreon_id TEXT PRIMARY KEY,
    member_id       TEXT NOT NULL DEFAULT '',
    attivo          BOOLEAN NOT NULL DEFAULT FALSE,
    tiers           TEXT[] NOT NULL DEFAULT '{}',
    aggiornato_il   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS patreon_eventi (
    impronta    TEXT PRIMARY KEY,
    tipo        TEXT NOT NULL,
    ricevuto_il TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_patreon_eventi_data ON patreon_eventi (ricevuto_il);

CREATE TABLE IF NOT EXISTS patreon_stati (
    impronta        TEXT PRIMARY KEY,
    discord_user_id BIGINT NOT NULL,
    scade_il        TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS patreon_livelli (
    tier_id TEXT PRIMARY KEY CHECK (char_length(tier_id) BETWEEN 1 AND 40),
    livello TEXT NOT NULL CHECK (livello IN ('premium', 'ultra', 'vip'))
);
