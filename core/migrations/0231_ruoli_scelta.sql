-- Catalogo #123 (RUO-090..093): ruoli che un membro può prendersi e lasciare da solo.
CREATE TABLE IF NOT EXISTS self_roles (
    guild_id   BIGINT NOT NULL,
    role_id    BIGINT NOT NULL,
    created_by BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (guild_id, role_id)
);
