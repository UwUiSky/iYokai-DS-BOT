-- #139 (parte senza AI): risposte standard imparate dallo staff e sollecito dopo N minuti.
-- Tutto si accende per pannello. Le risposte restano nel server dove sono nate (D19).

ALTER TABLE ticket_panels ADD COLUMN IF NOT EXISTS standard_attive BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE ticket_panels ADD COLUMN IF NOT EXISTS sollecito_minuti INTEGER
    CHECK (sollecito_minuti IS NULL OR sollecito_minuti BETWEEN 1 AND 1440);
ALTER TABLE ticket_panels ADD COLUMN IF NOT EXISTS ruolo_escalation BIGINT;

ALTER TABLE tickets ADD COLUMN IF NOT EXISTS utente_scritto_at TIMESTAMPTZ;
ALTER TABLE tickets ADD COLUMN IF NOT EXISTS sollecito_at TIMESTAMPTZ;
ALTER TABLE tickets ADD COLUMN IF NOT EXISTS escalato_at TIMESTAMPTZ;
ALTER TABLE tickets ADD COLUMN IF NOT EXISTS standard_reply_id INTEGER;

CREATE TABLE IF NOT EXISTS ticket_standard_replies (
    id                   SERIAL PRIMARY KEY,
    guild_id             BIGINT NOT NULL,
    panel_id             INTEGER NOT NULL REFERENCES ticket_panels(id) ON DELETE CASCADE,
    title                TEXT NOT NULL,
    keywords             TEXT NOT NULL,
    body                 TEXT NOT NULL,
    attachments          JSONB NOT NULL DEFAULT '[]'::jsonb,
    status               TEXT NOT NULL DEFAULT 'proposed' CHECK (status IN ('proposed', 'approved')),
    source_ticket_number INTEGER,
    approved_by          BIGINT,
    proposal_message_id  BIGINT,
    use_count            INTEGER NOT NULL DEFAULT 0,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    approved_at          TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_ticket_standard_guild_stato ON ticket_standard_replies (guild_id, status);
