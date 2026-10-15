-- M 12.17, #121, NF-39: copie datate della struttura del server (al massimo 10
-- per server) e modelli condivisibili con un codice.
CREATE TABLE IF NOT EXISTS backup_strutture (
    id              BIGSERIAL PRIMARY KEY,
    guild_id        BIGINT NOT NULL,
    nome            TEXT NOT NULL CHECK (char_length(nome) BETWEEN 1 AND 50),
    created_by      BIGINT NOT NULL,
    creato_il       TIMESTAMPTZ NOT NULL DEFAULT now(),
    dati            JSONB NOT NULL,
    codice_modello  TEXT UNIQUE
);
CREATE INDEX IF NOT EXISTS idx_backup_strutture_guild ON backup_strutture (guild_id, creato_il DESC);

-- BKP-009/010: stato di un caricamento e richiesta di annullo.
CREATE TABLE IF NOT EXISTS backup_caricamenti (
    id             BIGSERIAL PRIMARY KEY,
    guild_id       BIGINT NOT NULL,
    created_by     BIGINT NOT NULL,
    fonte          TEXT NOT NULL,
    stato          TEXT NOT NULL DEFAULT 'in_corso'
                   CHECK (stato IN ('in_corso', 'finito', 'annullato', 'fallito')),
    passo          TEXT NOT NULL DEFAULT '',
    fatti          INTEGER NOT NULL DEFAULT 0,
    totale         INTEGER NOT NULL DEFAULT 0,
    annulla        BOOLEAN NOT NULL DEFAULT false,
    creato_il      TIMESTAMPTZ NOT NULL DEFAULT now(),
    aggiornato_il  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_backup_caricamenti_in_corso
    ON backup_caricamenti (guild_id) WHERE stato = 'in_corso';

-- BKP-019: chi ha usato backup, modelli e sincronie (365 giorni).
CREATE TABLE IF NOT EXISTS backup_registro (
    id         BIGSERIAL PRIMARY KEY,
    guild_id   BIGINT NOT NULL,
    user_id    BIGINT NOT NULL,
    azione     TEXT NOT NULL,
    dettaglio  TEXT NOT NULL DEFAULT '' CHECK (char_length(dettaglio) <= 200),
    creato_il  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_backup_registro_guild ON backup_registro (guild_id, creato_il DESC);
