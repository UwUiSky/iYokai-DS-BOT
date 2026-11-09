-- D69 B12: nome per un codice d'invito, con un ruolo da dare a chi entra con quel codice.
CREATE TABLE IF NOT EXISTS inviti_etichette (
    guild_id  BIGINT NOT NULL,
    codice    TEXT   NOT NULL CHECK (char_length(codice) BETWEEN 2 AND 64),
    etichetta TEXT   NOT NULL CHECK (char_length(etichetta) BETWEEN 1 AND 50),
    ruolo_id  BIGINT,
    PRIMARY KEY (guild_id, codice)
);
