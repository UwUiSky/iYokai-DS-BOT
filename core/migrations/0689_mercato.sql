-- #125 r6eco (ECO-074, 120): mercato tra utenti con offerte (l'oggetto e le monete dell'offerta restano in custodia) e fondo premi.
CREATE TABLE IF NOT EXISTS economia_mercato (
    id         BIGSERIAL PRIMARY KEY,
    guild_id   BIGINT  NOT NULL,
    venditore  BIGINT  NOT NULL,
    item_id    INTEGER NOT NULL,
    quantita   INTEGER NOT NULL CHECK (quantita BETWEEN 1 AND 100),
    prezzo     BIGINT  NOT NULL CHECK (prezzo BETWEEN 1 AND 100000000),
    creato_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    scade_at   TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS economia_mercato_server ON economia_mercato (guild_id, scade_at);
CREATE INDEX IF NOT EXISTS economia_mercato_venditore ON economia_mercato (guild_id, venditore);

CREATE TABLE IF NOT EXISTS economia_mercato_offerte (
    annuncio_id BIGINT NOT NULL REFERENCES economia_mercato(id) ON DELETE CASCADE,
    offerente   BIGINT NOT NULL,
    importo     BIGINT NOT NULL CHECK (importo > 0),
    PRIMARY KEY (annuncio_id, offerente)
);
