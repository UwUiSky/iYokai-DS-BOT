-- #131 B3 (D70): classifiche delle gare (dado, spinner, e poi quiz, battitura, acronimi) in una tabella sola,
-- e il mazzo di carte condiviso di ogni server.
CREATE TABLE IF NOT EXISTS fun_punteggi (
    guild_id   BIGINT NOT NULL,
    gara       TEXT NOT NULL,
    periodo    TEXT NOT NULL,
    user_id    BIGINT NOT NULL,
    valore     BIGINT NOT NULL DEFAULT 0,
    aggiornato TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (guild_id, gara, periodo, user_id)
);
CREATE INDEX IF NOT EXISTS idx_fun_punteggi_classifica ON fun_punteggi (guild_id, gara, periodo, valore DESC);
CREATE TABLE IF NOT EXISTS fun_mazzi (
    guild_id     BIGINT PRIMARY KEY,
    rimaste      TEXT NOT NULL,
    mescolato_il TIMESTAMPTZ NOT NULL DEFAULT now()
);
