-- 23.17 (D49): missioni del giorno, serie, traguardi e stagione mensile.
CREATE TABLE IF NOT EXISTS progress_missioni (
    guild_id   BIGINT NOT NULL,
    user_id    BIGINT NOT NULL,
    giorno     DATE NOT NULL,
    chiave     TEXT NOT NULL,
    progresso  INTEGER NOT NULL DEFAULT 0,
    riscattata BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (guild_id, user_id, giorno, chiave)
);

CREATE TABLE IF NOT EXISTS progress_serie (
    guild_id      BIGINT NOT NULL,
    user_id       BIGINT NOT NULL,
    serie         INTEGER NOT NULL DEFAULT 0,
    record        INTEGER NOT NULL DEFAULT 0,
    ultimo_giorno DATE,
    PRIMARY KEY (guild_id, user_id)
);

CREATE TABLE IF NOT EXISTS progress_traguardi (
    guild_id    BIGINT NOT NULL,
    user_id     BIGINT NOT NULL,
    chiave      TEXT NOT NULL,
    ottenuto_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (guild_id, user_id, chiave)
);

CREATE TABLE IF NOT EXISTS progress_stagione (
    guild_id   BIGINT NOT NULL,
    user_id    BIGINT NOT NULL,
    stagione   TEXT NOT NULL,
    riscattati INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (guild_id, user_id, stagione)
);
