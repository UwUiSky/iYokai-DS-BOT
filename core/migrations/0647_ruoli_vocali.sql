-- Catalogo #123 (RUO-044): ruolo dato a chi è in un canale vocale e tolto quando esce.
CREATE TABLE IF NOT EXISTS voice_roles (
    guild_id   BIGINT NOT NULL,
    channel_id BIGINT NOT NULL,
    role_id    BIGINT NOT NULL,
    created_by BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (guild_id, channel_id)
);
