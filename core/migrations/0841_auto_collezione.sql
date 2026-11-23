-- FUN-017 (D111, D117, #131): auto da collezione, garage personale e foto delle proprie auto (solo la copia PNG ricodificata, D74).
CREATE TABLE IF NOT EXISTS fun_auto_garage (
    id         BIGSERIAL PRIMARY KEY,
    guild_id   BIGINT NOT NULL,
    user_id    BIGINT NOT NULL,
    modello    TEXT NOT NULL CHECK (char_length(modello) BETWEEN 1 AND 40),
    motore     SMALLINT NOT NULL DEFAULT 0 CHECK (motore BETWEEN 0 AND 5),
    assetto    SMALLINT NOT NULL DEFAULT 0 CHECK (assetto BETWEEN 0 AND 5),
    gomme      SMALLINT NOT NULL DEFAULT 0 CHECK (gomme BETWEEN 0 AND 5),
    corse      INTEGER NOT NULL DEFAULT 0 CHECK (corse >= 0),
    vinte      INTEGER NOT NULL DEFAULT 0 CHECK (vinte >= 0),
    comprata_il TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (guild_id, user_id, modello)
);

CREATE TABLE IF NOT EXISTS fun_auto_foto (
    auto_id     BIGINT PRIMARY KEY REFERENCES fun_auto_garage (id) ON DELETE CASCADE,
    guild_id    BIGINT NOT NULL,
    user_id     BIGINT NOT NULL,
    png         BYTEA NOT NULL CHECK (octet_length(png) BETWEEN 1 AND 2097152),
    sha256      TEXT NOT NULL CHECK (char_length(sha256) = 64),
    caricata_il TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_fun_auto_foto_utente ON fun_auto_foto (guild_id, user_id);
