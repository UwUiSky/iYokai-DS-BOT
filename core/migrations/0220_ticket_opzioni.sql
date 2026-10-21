-- #120 (catalogo ticket): opzioni dei pannelli, accesso, lista nera, sospensione,
-- staff reperibile, richiesta di chiusura, ruoli dati durante il ticket.

-- Una riga per pannello; senza riga valgono i valori predefiniti (core/ticket_opzioni_logic.py).
CREATE TABLE IF NOT EXISTS ticket_panel_opzioni (
    panel_id            INTEGER PRIMARY KEY REFERENCES ticket_panels(id) ON DELETE CASCADE,
    max_aperti          INTEGER CHECK (max_aperti IS NULL OR max_aperti BETWEEN 1 AND 500),      -- TKT-017
    ruoli_esenti        BIGINT[] NOT NULL DEFAULT '{}',                                           -- TKT-018
    pausa_secondi       INTEGER NOT NULL DEFAULT 0 CHECK (pausa_secondi BETWEEN 0 AND 604800),     -- TKT-019
    orari               TEXT,                                                                     -- TKT-022
    fuso                TEXT NOT NULL DEFAULT 'Europe/Rome',
    fuori_orario_testo  TEXT,                                                                     -- TKT-023
    fuori_orario_apri   BOOLEAN NOT NULL DEFAULT FALSE,
    nome_modello        TEXT,                                                                     -- TKT-025
    categorie_riserva   BIGINT[] NOT NULL DEFAULT '{}',                                           -- TKT-030
    ping_ruoli          BIGINT[] NOT NULL DEFAULT '{}',                                           -- TKT-037
    ping_here           BOOLEAN NOT NULL DEFAULT FALSE,
    ping_cancella       BOOLEAN NOT NULL DEFAULT FALSE,
    fissa_primo         BOOLEAN NOT NULL DEFAULT FALSE,                                           -- TKT-038
    dm_apertura         TEXT,                                                                     -- TKT-039
    dm_chiusura         TEXT,
    permessi_negati     TEXT[] NOT NULL DEFAULT '{}',                                             -- TKT-041
    ruoli_osservatori   BIGINT[] NOT NULL DEFAULT '{}',                                           -- TKT-042
    ruoli_durante       BIGINT[] NOT NULL DEFAULT '{}',                                           -- TKT-043
    ruoli_staff         BIGINT[] NOT NULL DEFAULT '{}',                                           -- TKT-044
    categoria_presi     BIGINT,                                                                   -- TKT-028
    claim_esclusivo     TEXT NOT NULL DEFAULT 'no' CHECK (claim_esclusivo IN ('no', 'scrivere', 'vedere')), -- TKT-050
    assegna_auto        BOOLEAN NOT NULL DEFAULT FALSE,                                           -- TKT-052
    testo_presa         TEXT,                                                                     -- TKT-053
    testo_rilascio      TEXT,
    conferma_chiusura   BOOLEAN NOT NULL DEFAULT FALSE,                                           -- TKT-054
    utente_chiude       BOOLEAN NOT NULL DEFAULT TRUE,                                            -- TKT-057
    transcript_dm       BOOLEAN NOT NULL DEFAULT TRUE                                             -- TKT-075
);

-- TKT-020: chi può aprire, regole lette dall'alto (la prima che tocca un ruolo dell'utente decide).
CREATE TABLE IF NOT EXISTS ticket_panel_accesso (
    panel_id  INTEGER NOT NULL REFERENCES ticket_panels(id) ON DELETE CASCADE,
    posizione SMALLINT NOT NULL CHECK (posizione BETWEEN 1 AND 25),
    role_id   BIGINT NOT NULL,
    permetti  BOOLEAN NOT NULL,
    PRIMARY KEY (panel_id, role_id)
);

-- TKT-021: utenti e ruoli che non possono aprire ticket (anche l'ID di chi è uscito).
CREATE TABLE IF NOT EXISTS ticket_blacklist (
    guild_id   BIGINT NOT NULL,
    target_id  BIGINT NOT NULL,
    is_role    BOOLEAN NOT NULL,
    motivo     TEXT,
    added_by   BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (guild_id, target_id)
);

-- TKT-024: apertura sospesa per il server, con motivo e fine facoltativa.
CREATE TABLE IF NOT EXISTS ticket_sospensioni (
    guild_id   BIGINT PRIMARY KEY,
    fino_a     TIMESTAMPTZ,
    motivo     TEXT NOT NULL,
    set_by     BIGINT
);

-- TKT-019: azzeramento della pausa tra due aperture, fatto dallo staff.
CREATE TABLE IF NOT EXISTS ticket_pause_azzerate (
    guild_id    BIGINT NOT NULL,
    user_id     BIGINT NOT NULL,
    azzerata_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (guild_id, user_id)
);

-- TKT-033: staff reperibile, aggiunto e avvisato a ogni nuovo ticket.
CREATE TABLE IF NOT EXISTS ticket_reperibili (
    guild_id BIGINT NOT NULL,
    user_id  BIGINT NOT NULL,
    PRIMARY KEY (guild_id, user_id)
);

ALTER TABLE tickets ADD COLUMN IF NOT EXISTS chiusura_richiesta_at TIMESTAMPTZ; -- TKT-055
ALTER TABLE tickets ADD COLUMN IF NOT EXISTS ruoli_dati BIGINT[] NOT NULL DEFAULT '{}'; -- TKT-043
ALTER TABLE tickets ADD COLUMN IF NOT EXISTS note_thread_id BIGINT; -- TKT-034
CREATE INDEX IF NOT EXISTS idx_tickets_pannello_aperti ON tickets (panel_id) WHERE status = 'open';
CREATE INDEX IF NOT EXISTS idx_tickets_utente_creato ON tickets (guild_id, user_id, created_at DESC);
