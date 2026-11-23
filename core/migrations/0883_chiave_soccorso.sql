-- SIC-021 (D121): la chiave di soccorso dell'owner. Una sola riga; del codice resta solo l'impronta.
CREATE TABLE IF NOT EXISTS owner_chiave_soccorso (
    id            SMALLINT PRIMARY KEY CHECK (id = 1),
    sale          BYTEA   NOT NULL,
    impronta      BYTEA   NOT NULL,
    creata_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    errori        INTEGER NOT NULL DEFAULT 0,
    ultimo_errore TIMESTAMPTZ,
    ultimo_uso    TIMESTAMPTZ
);
