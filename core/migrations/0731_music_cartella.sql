-- #126 (MUS-018, MUS-015): brani della cartella dell'owner e impostazioni globali dell'owner per la musica.
-- Il percorso e' relativo alla cartella e non esce mai dal bot verso gli utenti.
CREATE TABLE IF NOT EXISTS music_cartella_brani (
    id           BIGSERIAL   PRIMARY KEY,
    percorso     TEXT        NOT NULL UNIQUE CHECK (char_length(percorso) BETWEEN 1 AND 500),
    titolo       TEXT        NOT NULL CHECK (char_length(titolo) BETWEEN 1 AND 100),
    durata_ms    BIGINT      CHECK (durata_ms IS NULL OR durata_ms >= 0),
    dimensione   BIGINT      NOT NULL CHECK (dimensione >= 0),
    modificato_ns BIGINT     NOT NULL,
    visto_il     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS music_owner_impostazioni (
    chiave      TEXT        PRIMARY KEY CHECK (char_length(chiave) BETWEEN 1 AND 40),
    valore      TEXT        NOT NULL CHECK (char_length(valore) <= 100),
    cambiata_da BIGINT      NOT NULL,
    cambiata_il TIMESTAMPTZ NOT NULL DEFAULT now()
);
