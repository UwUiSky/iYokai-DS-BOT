-- D69 B16: citazioni del server (max 500, testo <= 1000) e conteggio dei comandi usati per server e giorno (90 giorni).
CREATE TABLE IF NOT EXISTS citazioni (
    id          BIGSERIAL PRIMARY KEY,
    guild_id    BIGINT NOT NULL,
    autore_id   BIGINT,
    testo       TEXT NOT NULL CHECK (char_length(testo) BETWEEN 1 AND 1000),
    aggiunta_da BIGINT NOT NULL,
    link        TEXT CHECK (char_length(link) <= 200),
    creata_il   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_citazioni_server ON citazioni (guild_id);

CREATE TABLE IF NOT EXISTS comandi_uso_server (
    guild_id BIGINT NOT NULL,
    comando  TEXT NOT NULL,
    giorno   DATE NOT NULL,
    usi      INT NOT NULL DEFAULT 0,
    PRIMARY KEY (guild_id, giorno, comando)
);
