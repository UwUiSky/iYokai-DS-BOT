-- #120: TKT-062 (escludere un ticket dalla chiusura automatica), TKT-066 (questionario dopo il voto),
-- TKT-076 (un interruttore per ogni azione registrata nel log dei ticket).
ALTER TABLE tickets ADD COLUMN IF NOT EXISTS tieni_aperto BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE ticket_panels ADD COLUMN IF NOT EXISTS questionario VARCHAR(45);
CREATE TABLE IF NOT EXISTS ticket_questionario_risposte (
    ticket_id  INTEGER PRIMARY KEY REFERENCES tickets(id) ON DELETE CASCADE,
    guild_id   BIGINT NOT NULL,
    user_id    BIGINT NOT NULL,
    risposta   VARCHAR(1000) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_ticket_questionario_utente ON ticket_questionario_risposte (guild_id, user_id);

CREATE TABLE IF NOT EXISTS ticket_log_azioni (
    guild_id BIGINT NOT NULL,
    azione   VARCHAR(20) NOT NULL,
    acceso   BOOLEAN NOT NULL,
    PRIMARY KEY (guild_id, azione)
);
