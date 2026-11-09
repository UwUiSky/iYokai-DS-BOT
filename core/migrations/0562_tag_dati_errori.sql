-- D69 B26: dati per server degli script dei tag ({dati:...}) e ultimi errori degli script (10 per tag).
CREATE TABLE IF NOT EXISTS tag_dati (
    guild_id    BIGINT NOT NULL,
    chiave      TEXT   NOT NULL CHECK (char_length(chiave) BETWEEN 1 AND 64),
    valore      TEXT   NOT NULL CHECK (octet_length(valore) <= 1024),
    aggiornato  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (guild_id, chiave)
);

CREATE TABLE IF NOT EXISTS tag_errori (
    id        BIGSERIAL PRIMARY KEY,
    guild_id  BIGINT NOT NULL,
    tag       TEXT   NOT NULL,
    chiave    TEXT   NOT NULL,
    dettaglio TEXT   NOT NULL DEFAULT '',
    creato_il TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_tag_errori_tag ON tag_errori (guild_id, tag, id DESC);
