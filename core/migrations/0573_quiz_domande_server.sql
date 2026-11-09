-- #131 B6 (D70): domande del quiz caricate dal server (la prima risposta è la giusta; il bot le mescola).
CREATE TABLE IF NOT EXISTS quiz_domande_server (
    id        BIGSERIAL PRIMARY KEY,
    guild_id  BIGINT NOT NULL,
    tema      TEXT NOT NULL DEFAULT '',
    domanda   TEXT NOT NULL,
    risposte  JSONB NOT NULL,
    autore_id BIGINT NOT NULL,
    creata    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_quiz_domande_server ON quiz_domande_server (guild_id, id);
