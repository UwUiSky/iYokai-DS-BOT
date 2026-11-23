-- TKT-072 (#120, D111): trascrizioni dei ticket conservate cifrate, per 90 giorni al massimo.
-- Il contenuto sta solo in `cifrato` (AES-256-GCM, chiave nel file .env, mai qui). Le colonne in chiaro servono alla
-- ricerca dello staff: chi ha aperto, pannello, numero. Voto e motivo si leggono dalla riga del ticket.
CREATE TABLE IF NOT EXISTS ticket_trascrizioni (
    id            BIGSERIAL PRIMARY KEY,
    guild_id      BIGINT NOT NULL,
    ticket_id     BIGINT NOT NULL,
    ticket_number INTEGER NOT NULL,
    user_id       BIGINT NOT NULL,
    panel_id      BIGINT,
    cifrato       TEXT NOT NULL,
    peso          INTEGER NOT NULL DEFAULT 0,
    creata_il     TIMESTAMPTZ NOT NULL DEFAULT now(),
    scade_il      TIMESTAMPTZ NOT NULL,
    UNIQUE (guild_id, ticket_id)
);
CREATE INDEX IF NOT EXISTS ix_ticket_trascrizioni_server ON ticket_trascrizioni (guild_id, creata_il DESC);
CREATE INDEX IF NOT EXISTS ix_ticket_trascrizioni_utente ON ticket_trascrizioni (user_id);
CREATE INDEX IF NOT EXISTS ix_ticket_trascrizioni_scadenza ON ticket_trascrizioni (scade_il);

-- Per server: accesa di base, 90 giorni (il massimo). Il server può accorciare o spegnere.
CREATE TABLE IF NOT EXISTS ticket_trascrizioni_opzioni (
    guild_id BIGINT PRIMARY KEY,
    attiva   BOOLEAN NOT NULL DEFAULT TRUE,
    giorni   INTEGER NOT NULL DEFAULT 90 CHECK (giorni BETWEEN 1 AND 90)
);

-- Il file HTML della trascrizione c'è di base (D111); chi aveva scelto altro lo conserva.
ALTER TABLE ticket_panel_opzioni ALTER COLUMN transcript_formato SET DEFAULT 'entrambi';
