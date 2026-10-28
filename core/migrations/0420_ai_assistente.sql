-- NF-24 (r12): preferenza personale dell'assistente AI e traguardi legati all'AI.
CREATE TABLE IF NOT EXISTS ai_utenti (
    user_id        BIGINT PRIMARY KEY,
    assistente     BOOLEAN NOT NULL DEFAULT TRUE,
    aggiornato_il  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ai_traguardi (
    user_id     BIGINT NOT NULL,
    codice      TEXT NOT NULL,
    ottenuto_il TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, codice)
);
