-- ECO-160 (D121): sospensione dal gioco (monete, giochi, clan) decisa dallo staff del server, con richiesta di revisione.
CREATE TABLE IF NOT EXISTS economia_sospensioni (
    guild_id      BIGINT NOT NULL,
    user_id       BIGINT NOT NULL,
    motivo        TEXT   NOT NULL,
    fino_a        TIMESTAMPTZ,
    sospeso_da    BIGINT NOT NULL,
    creato_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    appello       TEXT,
    appello_stato TEXT NOT NULL DEFAULT 'nessuno' CHECK (appello_stato IN ('nessuno', 'aperto', 'respinto')),
    appello_at    TIMESTAMPTZ,
    deciso_da     BIGINT,
    PRIMARY KEY (guild_id, user_id)
);
