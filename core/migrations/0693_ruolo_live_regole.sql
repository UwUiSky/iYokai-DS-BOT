-- #129 (ALR-042..048): regole del ruolo «in diretta» (fino a 5 per server), con esclusi, eccezioni e annuncio.
CREATE TABLE IF NOT EXISTS live_role_regole (
    id                  SERIAL PRIMARY KEY,
    guild_id            BIGINT NOT NULL,
    role_id             BIGINT NOT NULL,
    only_role_id        BIGINT,
    keywords            TEXT NOT NULL DEFAULT '',
    games               TEXT NOT NULL DEFAULT '',
    announce_channel_id BIGINT,
    announce_template   TEXT NOT NULL DEFAULT '',
    announce_gap_minutes INTEGER NOT NULL DEFAULT 360,
    created_by          BIGINT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_live_role_regole_guild ON live_role_regole (guild_id);

-- tipo: escluso_ruolo, escluso_membro (mai il ruolo), eccezione (riceve il ruolo anche senza parole o gioco)
CREATE TABLE IF NOT EXISTS live_role_voci (
    regola_id INTEGER NOT NULL REFERENCES live_role_regole (id) ON DELETE CASCADE,
    guild_id  BIGINT NOT NULL,
    tipo      TEXT NOT NULL,
    target_id BIGINT NOT NULL,
    PRIMARY KEY (regola_id, tipo, target_id)
);
