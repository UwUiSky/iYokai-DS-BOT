-- #125 r6eco (ECO-135..137, 139..141): profilo di pesca (abilità, perle, attrezzi, rete), pass stagionale, storico.
CREATE TABLE IF NOT EXISTS economia_pesca_profilo (
    guild_id BIGINT NOT NULL,
    user_id  BIGINT NOT NULL,
    lanci    INTEGER NOT NULL DEFAULT 0,
    pescati  INTEGER NOT NULL DEFAULT 0,
    perle    BIGINT  NOT NULL DEFAULT 0 CHECK (perle >= 0),
    esche    INTEGER NOT NULL DEFAULT 0 CHECK (esche >= 0),
    canna    INTEGER NOT NULL DEFAULT 0 CHECK (canna BETWEEN 0 AND 3),
    rete_at  TIMESTAMPTZ,
    abilita  TEXT    NOT NULL DEFAULT '',
    PRIMARY KEY (guild_id, user_id)
);
CREATE TABLE IF NOT EXISTS economia_pesca_stagione (
    guild_id  BIGINT NOT NULL,
    user_id   BIGINT NOT NULL,
    stagione  TEXT   NOT NULL,
    punti     BIGINT NOT NULL DEFAULT 0,
    riscossi  INTEGER NOT NULL DEFAULT 0 CHECK (riscossi BETWEEN 0 AND 10),
    PRIMARY KEY (guild_id, user_id, stagione)
);
CREATE TABLE IF NOT EXISTS economia_pesca_storico (
    id       BIGSERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    user_id  BIGINT NOT NULL,
    quando   TIMESTAMPTZ NOT NULL DEFAULT now(),
    tipo     TEXT   NOT NULL,
    specie   TEXT,
    valore   BIGINT NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS economia_pesca_storico_utente ON economia_pesca_storico (guild_id, user_id, id DESC);
