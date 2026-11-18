-- #125 B5 (ECO-057): evento di monete in un canale, avviato e chiuso dallo staff, con tetto di monete distribuite.
CREATE TABLE IF NOT EXISTS economia_eventi (
    id             BIGSERIAL PRIMARY KEY,
    guild_id       BIGINT  NOT NULL,
    channel_id     BIGINT  NOT NULL,
    per_messaggio  INTEGER NOT NULL CHECK (per_messaggio > 0),
    tetto          BIGINT  NOT NULL CHECK (tetto > 0),
    distribuito    BIGINT  NOT NULL DEFAULT 0 CHECK (distribuito >= 0),
    attivo         BOOLEAN NOT NULL DEFAULT TRUE,
    avviato_da     BIGINT  NOT NULL,
    avviato_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- Un solo evento attivo per server.
CREATE UNIQUE INDEX IF NOT EXISTS economia_eventi_uno_attivo ON economia_eventi (guild_id) WHERE attivo;
