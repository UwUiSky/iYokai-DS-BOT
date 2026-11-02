-- TKT-079: articoli della base di conoscenza dei ticket (cercabili, inviabili a mano e suggeriti all'apertura).
-- Al massimo 200 per server; `parole` sono le parole chiave per il suggerimento (senza AI).
CREATE TABLE IF NOT EXISTS ticket_articoli (
    id        SERIAL PRIMARY KEY,
    guild_id  BIGINT NOT NULL,
    titolo    VARCHAR(100) NOT NULL,
    testo     VARCHAR(4000) NOT NULL,
    parole    TEXT NOT NULL DEFAULT '',
    approvato BOOLEAN NOT NULL DEFAULT TRUE,
    creato_da BIGINT,
    usi       INTEGER NOT NULL DEFAULT 0,
    creato_il TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_ticket_articoli_server ON ticket_articoli (guild_id);
