-- M 12.12 (#68): chi ha accettato, a fine verifica, di ricevere un DM se il
-- server deve essere ripristinato. Senza riga (e senza token OAuth) niente DM.
CREATE TABLE IF NOT EXISTS restore_consensi (
    guild_id  BIGINT NOT NULL,
    user_id   BIGINT NOT NULL,
    dato_il   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (guild_id, user_id)
);
