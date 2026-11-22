-- #125 r6eco (ECO-075, 076, 078): rotazione degli oggetti, offerte lampo a tempo, ricette.
ALTER TABLE shop_items ADD COLUMN IF NOT EXISTS a_rotazione BOOLEAN NOT NULL DEFAULT FALSE;

CREATE TABLE IF NOT EXISTS economia_negozio_conf (
    guild_id         BIGINT PRIMARY KEY,
    rotazione_quanti INTEGER NOT NULL DEFAULT 0 CHECK (rotazione_quanti BETWEEN 0 AND 25)
);

CREATE TABLE IF NOT EXISTS economia_offerte (
    id         BIGSERIAL PRIMARY KEY,
    guild_id   BIGINT  NOT NULL,
    item_id    INTEGER NOT NULL,
    sconto_pct INTEGER NOT NULL CHECK (sconto_pct BETWEEN 1 AND 90),
    scade_at   TIMESTAMPTZ NOT NULL,
    usi_max    INTEGER CHECK (usi_max IS NULL OR usi_max > 0),
    usi        INTEGER NOT NULL DEFAULT 0,
    creata_da  BIGINT NOT NULL,
    UNIQUE (guild_id, item_id)
);

CREATE TABLE IF NOT EXISTS economia_ricette (
    id             BIGSERIAL PRIMARY KEY,
    guild_id       BIGINT  NOT NULL,
    nome           TEXT    NOT NULL CHECK (char_length(nome) BETWEEN 1 AND 40),
    risultato_item INTEGER NOT NULL,
    risultato_q    INTEGER NOT NULL DEFAULT 1 CHECK (risultato_q BETWEEN 1 AND 100),
    costo          INTEGER NOT NULL DEFAULT 0 CHECK (costo BETWEEN 0 AND 1000000),
    UNIQUE (guild_id, nome)
);

CREATE TABLE IF NOT EXISTS economia_ricette_ingredienti (
    ricetta_id BIGINT  NOT NULL REFERENCES economia_ricette(id) ON DELETE CASCADE,
    item_id    INTEGER NOT NULL,
    quantita   INTEGER NOT NULL CHECK (quantita BETWEEN 1 AND 100),
    PRIMARY KEY (ricetta_id, item_id)
);
