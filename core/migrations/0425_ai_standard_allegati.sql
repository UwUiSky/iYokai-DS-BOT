-- NF-24 (r12): archivio durevole dei file delle risposte standard dei ticket (AI-R-104): restano nel database,
-- non solo come link nel canale dei log che si può cancellare. Spariscono con la risposta.
CREATE TABLE IF NOT EXISTS ai_standard_allegati (
    id        SERIAL PRIMARY KEY,
    guild_id  BIGINT  NOT NULL,
    reply_id  INTEGER NOT NULL REFERENCES ticket_standard_replies(id) ON DELETE CASCADE,
    filename  TEXT    NOT NULL,
    contenuto BYTEA   NOT NULL,
    creato_il TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ai_standard_allegati_reply ON ai_standard_allegati (reply_id);
