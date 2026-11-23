-- AI-003, D59, D127: chiavi API di un server o di un utente per i servizi AI. Sempre cifrate; mai in chiaro.
CREATE TABLE IF NOT EXISTS ai_chiavi_proprie (
    ambito        TEXT NOT NULL CHECK (ambito IN ('utente', 'server')),
    ambito_id     BIGINT NOT NULL,
    servizio      TEXT NOT NULL CHECK (servizio ~ '^[a-z0-9_]{1,40}$'),
    chiave_cifrata TEXT NOT NULL,
    messa_da      BIGINT NOT NULL,
    creato_il     TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (ambito, ambito_id, servizio)
);
