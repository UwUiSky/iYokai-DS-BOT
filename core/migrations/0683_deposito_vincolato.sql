-- #125 B14 (ECO-005): deposito vincolato, un solo deposito per persona.
CREATE TABLE IF NOT EXISTS economia_depositi (
    guild_id BIGINT NOT NULL,
    user_id  BIGINT NOT NULL,
    importo  BIGINT NOT NULL CHECK (importo > 0),
    scade_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (guild_id, user_id)
);
