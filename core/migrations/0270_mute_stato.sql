-- Mute con ruolo a tempo, hardmute e mute che resta al rientro (MOD-014, 015, 021).
-- Una riga per utente silenziato: serve per rimettere il ruolo se rientra, per ridare
-- i ruoli tolti da un hardmute e per sapere quando finisce.
CREATE TABLE IF NOT EXISTS mute_stato (
    guild_id     BIGINT NOT NULL,
    user_id      BIGINT NOT NULL,
    hard         BOOLEAN NOT NULL DEFAULT FALSE,
    ruoli        BIGINT[] NOT NULL DEFAULT '{}',
    case_number  INTEGER,
    finisce_il   TIMESTAMPTZ,
    PRIMARY KEY (guild_id, user_id)
);
