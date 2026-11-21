-- #125 B15 (ECO-148, 149, 153, 154, 155, 159): amici, blocchi, matrimonio, prestigio.
CREATE TABLE IF NOT EXISTS economia_blocchi (
    user_id     BIGINT NOT NULL,
    bloccato_id BIGINT NOT NULL,
    PRIMARY KEY (user_id, bloccato_id),
    CHECK (user_id <> bloccato_id)
);

-- Coppia ordinata (a < b): amici o sposati.
CREATE TABLE IF NOT EXISTS economia_amici (
    guild_id BIGINT NOT NULL,
    a        BIGINT NOT NULL,
    b        BIGINT NOT NULL,
    dal      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (guild_id, a, b),
    CHECK (a < b)
);
CREATE TABLE IF NOT EXISTS economia_matrimoni (
    guild_id BIGINT NOT NULL,
    a        BIGINT NOT NULL,
    b        BIGINT NOT NULL,
    dal      TIMESTAMPTZ NOT NULL DEFAULT now(),
    mantenuto_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (guild_id, a, b),
    CHECK (a < b)
);
CREATE UNIQUE INDEX IF NOT EXISTS economia_matrimoni_a ON economia_matrimoni (guild_id, a);
CREATE UNIQUE INDEX IF NOT EXISTS economia_matrimoni_b ON economia_matrimoni (guild_id, b);

CREATE TABLE IF NOT EXISTS economia_prestigio (
    guild_id BIGINT NOT NULL,
    user_id  BIGINT NOT NULL,
    livello  INTEGER NOT NULL DEFAULT 0 CHECK (livello BETWEEN 0 AND 5),
    PRIMARY KEY (guild_id, user_id)
);
