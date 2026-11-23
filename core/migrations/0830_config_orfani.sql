-- UTL-226 (D111): canali e ruoli citati nella configurazione che non esistono più. Si segna da quando mancano;
-- la configurazione si pulisce solo dopo 7 giorni.
CREATE TABLE IF NOT EXISTS config_orfani (
    guild_id      BIGINT      NOT NULL,
    tipo          TEXT        NOT NULL CHECK (tipo IN ('canale', 'ruolo')),
    oggetto_id    BIGINT      NOT NULL,
    mancante_dal  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (guild_id, tipo, oggetto_id)
);
