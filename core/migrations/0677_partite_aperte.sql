-- #125 B8 (ECO-088, 089): partite a più passi con la puntata già tolta; se il bot si ferma, la puntata torna a chi gioca.
CREATE TABLE IF NOT EXISTS economia_partite_aperte (
    id        BIGSERIAL PRIMARY KEY,
    guild_id  BIGINT NOT NULL,
    user_id   BIGINT NOT NULL,
    gioco     TEXT   NOT NULL,
    puntata   BIGINT NOT NULL CHECK (puntata > 0),
    scade_at  TIMESTAMPTZ NOT NULL,
    UNIQUE (guild_id, user_id)
);
