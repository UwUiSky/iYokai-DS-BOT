-- Catalogo #123 (RUO-045): ruolo personale gestito dal membro. role_id resta vuoto finché il membro non lo crea.
CREATE TABLE IF NOT EXISTS ruoli_personali (
    guild_id        BIGINT NOT NULL,
    user_id         BIGINT NOT NULL,
    role_id         BIGINT,
    concesso_da     BIGINT NOT NULL,
    ultima_modifica TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (guild_id, user_id)
);
