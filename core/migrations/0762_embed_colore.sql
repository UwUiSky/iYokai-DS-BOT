-- Catalogo #128 (UTL-084): colore predefinito degli embed del costruttore, uno per server.
CREATE TABLE IF NOT EXISTS embed_colori (
    guild_id BIGINT PRIMARY KEY,
    colore   TEXT NOT NULL CHECK (colore ~ '^#[0-9A-Fa-f]{6}$')
);
