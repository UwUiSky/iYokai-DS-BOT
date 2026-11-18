-- #125 B10 (ECO-081): potenziamenti personali a livelli (lavoro e premio periodico).
CREATE TABLE IF NOT EXISTS economia_potenziamenti (
    guild_id BIGINT NOT NULL,
    user_id  BIGINT NOT NULL,
    tipo     TEXT   NOT NULL CHECK (tipo IN ('lavoro', 'premio')),
    livello  INTEGER NOT NULL DEFAULT 0 CHECK (livello BETWEEN 0 AND 5),
    PRIMARY KEY (guild_id, user_id, tipo)
);
