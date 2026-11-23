-- VER-025 (D111, D112, #118): rete di protezione tra server. Avvisi, timeout per account compromessi, rete facoltativa dei ban.
CREATE TABLE IF NOT EXISTS rete_impostazioni (
    guild_id        BIGINT PRIMARY KEY,
    ricezione       BOOLEAN NOT NULL DEFAULT TRUE,
    canale_id       BIGINT,
    mostra_origine  BOOLEAN NOT NULL DEFAULT FALSE,
    timeout_ore     INTEGER NOT NULL DEFAULT 24 CHECK (timeout_ore BETWEEN 1 AND 672),
    ban_aderisce    BOOLEAN NOT NULL DEFAULT FALSE,
    ban_modo        TEXT NOT NULL DEFAULT 'proposta' CHECK (ban_modo IN ('proposta', 'automatico')),
    aderito_il      TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS rete_segnalazioni (
    id            BIGSERIAL PRIMARY KEY,
    user_id       BIGINT NOT NULL,
    guild_origine BIGINT NOT NULL,
    categoria     TEXT NOT NULL,
    gravita       TEXT NOT NULL,
    creata_il     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_rete_segnalazioni_utente ON rete_segnalazioni (user_id, categoria, creata_il);
CREATE INDEX IF NOT EXISTS idx_rete_segnalazioni_origine ON rete_segnalazioni (guild_origine, creata_il);

CREATE TABLE IF NOT EXISTS rete_consegne (
    id               BIGSERIAL PRIMARY KEY,
    segnalazione_id  BIGINT NOT NULL REFERENCES rete_segnalazioni (id) ON DELETE CASCADE,
    guild_id         BIGINT NOT NULL,
    consegnata_il    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_rete_consegne_server ON rete_consegne (guild_id, consegnata_il);

CREATE TABLE IF NOT EXISTS rete_server_bloccati (
    guild_id     BIGINT PRIMARY KEY,
    motivo       TEXT,
    bloccato_da  BIGINT,
    bloccato_il  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS rete_timeout (
    guild_id       BIGINT NOT NULL,
    user_id        BIGINT NOT NULL,
    origine_guild  BIGINT NOT NULL,
    fino_a         TIMESTAMPTZ NOT NULL,
    case_number    INTEGER,
    creato_il      TIMESTAMPTZ NOT NULL DEFAULT now(),
    annullato_da   BIGINT,
    annullato_il   TIMESTAMPTZ,
    PRIMARY KEY (guild_id, user_id)
);

CREATE TABLE IF NOT EXISTS rete_ban_proposte (
    id             BIGSERIAL PRIMARY KEY,
    user_id        BIGINT NOT NULL,
    guild_origine  BIGINT NOT NULL,
    guild_dest     BIGINT NOT NULL,
    categoria      TEXT NOT NULL,
    stato          TEXT NOT NULL DEFAULT 'proposta'
                   CHECK (stato IN ('proposta', 'applicato', 'rifiutato', 'annullato', 'fallito')),
    case_number    INTEGER,
    canale_id      BIGINT,
    messaggio_id   BIGINT,
    creata_il      TIMESTAMPTZ NOT NULL DEFAULT now(),
    deciso_da      BIGINT,
    deciso_il      TIMESTAMPTZ,
    UNIQUE (user_id, guild_origine, guild_dest)
);
CREATE INDEX IF NOT EXISTS idx_rete_ban_dest ON rete_ban_proposte (guild_dest, stato);
