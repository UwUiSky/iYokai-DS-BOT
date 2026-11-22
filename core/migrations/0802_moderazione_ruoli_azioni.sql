-- Catalogo CFG-024: permesso per singola azione di moderazione dato a un ruolo (anche senza il permesso di Discord).
CREATE TABLE IF NOT EXISTS moderation_ruoli_azioni (
    guild_id BIGINT NOT NULL,
    role_id  BIGINT NOT NULL,
    azione   TEXT   NOT NULL,
    dato_da  BIGINT,
    PRIMARY KEY (guild_id, role_id, azione)
);
