-- Ban temporaneo con rientro e ban in isolamento (issue #138):
-- ruoli salvati al momento del ban e invito da usare al ritorno.
CREATE TABLE IF NOT EXISTS tempban_stato (
    guild_id       BIGINT NOT NULL,
    user_id        BIGINT NOT NULL,
    modo           TEXT NOT NULL,
    ruoli          BIGINT[] NOT NULL DEFAULT '{}',
    invito_codice  TEXT,
    case_number    INTEGER,
    finisce_il     TIMESTAMPTZ NOT NULL,
    scaduto        BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (guild_id, user_id)
);
