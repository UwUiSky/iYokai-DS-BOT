-- D69 B27: inneschi dei tag (reazione, intervallo, orario, bottone, ruolo dato o tolto). Al massimo 25 per server.
CREATE TABLE IF NOT EXISTS tag_inneschi (
    id         BIGSERIAL PRIMARY KEY,
    guild_id   BIGINT NOT NULL,
    tag        TEXT   NOT NULL,
    tipo       TEXT   NOT NULL CHECK (tipo IN ('reazione', 'intervallo', 'orario', 'bottone', 'ruolo_dato', 'ruolo_tolto')),
    valore     TEXT   NOT NULL,
    canale_id  BIGINT,
    escludi    TEXT   NOT NULL DEFAULT '',
    creato_da  BIGINT,
    creato_il  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (guild_id, tag, tipo, valore)
);
CREATE INDEX IF NOT EXISTS idx_tag_inneschi_tipo ON tag_inneschi (guild_id, tipo);
