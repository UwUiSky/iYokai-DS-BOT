-- FUN-013, FUN-014 (D111, D117, #131): tela di pixel del server. Una tela 100x100 per server, 16 colori fissi, un pixel
-- ogni tanto per persona; si tiene chi ha messo ogni pixel (per toglierli) e chi è bloccato dalla tela.
CREATE TABLE IF NOT EXISTS tela_impostazioni (
    guild_id        BIGINT PRIMARY KEY,
    pubblica        BOOLEAN NOT NULL DEFAULT FALSE,
    pausa_secondi   INTEGER NOT NULL DEFAULT 300 CHECK (pausa_secondi BETWEEN 30 AND 3600),
    costo_minuto    INTEGER NOT NULL DEFAULT 10 CHECK (costo_minuto BETWEEN 0 AND 10000)
);

CREATE TABLE IF NOT EXISTS tela_pixel (
    guild_id   BIGINT NOT NULL,
    x          SMALLINT NOT NULL CHECK (x BETWEEN 0 AND 99),
    y          SMALLINT NOT NULL CHECK (y BETWEEN 0 AND 99),
    colore     SMALLINT NOT NULL CHECK (colore BETWEEN 0 AND 15),
    user_id    BIGINT NOT NULL,
    messo_il   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (guild_id, x, y)
);
CREATE INDEX IF NOT EXISTS idx_tela_pixel_utente ON tela_pixel (guild_id, user_id);

CREATE TABLE IF NOT EXISTS tela_utenti (
    guild_id      BIGINT NOT NULL,
    user_id       BIGINT NOT NULL,
    ultimo_at     TIMESTAMPTZ,
    pixel_messi   INTEGER NOT NULL DEFAULT 0 CHECK (pixel_messi >= 0),
    bloccato      BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (guild_id, user_id)
);
