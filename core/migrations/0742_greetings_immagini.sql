-- Catalogo #123 (RUO-012): immagini proprie del benvenuto (al massimo 10 per server), solo ricodificate.
CREATE TABLE IF NOT EXISTS greetings_images (
    id         SERIAL PRIMARY KEY,
    guild_id   BIGINT NOT NULL,
    image      BYTEA NOT NULL,
    added_by   BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_greetings_images_guild ON greetings_images (guild_id);
