-- D69 B22: sondaggio a bottoni del bot. Un sondaggio, le sue opzioni (max 20), i voti (solo mentre è aperto: alla chiusura
-- restano i totali in `sondaggi_opzioni.voti`) e i pesi per ruolo decisi dal server (max 25).
CREATE TABLE IF NOT EXISTS sondaggi (
    id            BIGSERIAL PRIMARY KEY,
    guild_id      BIGINT NOT NULL,
    channel_id    BIGINT NOT NULL,
    message_id    BIGINT,
    autore_id     BIGINT NOT NULL,
    domanda       TEXT   NOT NULL,
    anonimo       BOOLEAN NOT NULL DEFAULT FALSE,
    risultati     TEXT   NOT NULL DEFAULT 'subito' CHECK (risultati IN ('subito', 'alla_fine')),
    multipla      BOOLEAN NOT NULL DEFAULT FALSE,
    pesato        BOOLEAN NOT NULL DEFAULT FALSE,
    ruoli         BIGINT[] NOT NULL DEFAULT '{}',
    chiudi_a_voti INT CHECK (chiudi_a_voti IS NULL OR chiudi_a_voti BETWEEN 1 AND 100000),
    inizia_il     TIMESTAMPTZ,
    scade_il      TIMESTAMPTZ,
    durata_s      INT,
    stato         TEXT   NOT NULL DEFAULT 'aperto' CHECK (stato IN ('programmato', 'aperto', 'chiuso')),
    creato_il     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    chiuso_il     TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_sondaggi_server ON sondaggi (guild_id, stato);
CREATE INDEX IF NOT EXISTS idx_sondaggi_chiusi ON sondaggi (chiuso_il) WHERE stato = 'chiuso';

CREATE TABLE IF NOT EXISTS sondaggi_opzioni (
    sondaggio_id BIGINT NOT NULL REFERENCES sondaggi (id) ON DELETE CASCADE,
    n            INT    NOT NULL CHECK (n BETWEEN 0 AND 19),
    testo        TEXT   NOT NULL,
    voti         INT    NOT NULL DEFAULT 0,
    voti_pesati  INT    NOT NULL DEFAULT 0,
    PRIMARY KEY (sondaggio_id, n)
);

CREATE TABLE IF NOT EXISTS sondaggi_voti (
    guild_id     BIGINT NOT NULL,
    sondaggio_id BIGINT NOT NULL REFERENCES sondaggi (id) ON DELETE CASCADE,
    user_id      BIGINT NOT NULL,
    n            INT    NOT NULL,
    peso         INT    NOT NULL DEFAULT 1,
    PRIMARY KEY (sondaggio_id, user_id, n)
);
CREATE INDEX IF NOT EXISTS idx_sondaggi_voti_utente ON sondaggi_voti (user_id);

CREATE TABLE IF NOT EXISTS sondaggi_pesi (
    guild_id BIGINT NOT NULL,
    ruolo_id BIGINT NOT NULL,
    peso     INT    NOT NULL CHECK (peso BETWEEN 1 AND 100),
    PRIMARY KEY (guild_id, ruolo_id)
);
