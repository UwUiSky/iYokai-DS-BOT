-- NF-39 (#110): ban e ruoli tenuti uguali tra due server dello stesso proprietario.
-- guild_a < guild_b: una sola riga per coppia.
CREATE TABLE IF NOT EXISTS backup_sincronie (
    guild_a     BIGINT NOT NULL,
    guild_b     BIGINT NOT NULL,
    ban         BOOLEAN NOT NULL DEFAULT true,
    ruoli       BOOLEAN NOT NULL DEFAULT true,
    created_by  BIGINT NOT NULL,
    creato_il   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (guild_a, guild_b),
    CHECK (guild_a < guild_b)
);
CREATE INDEX IF NOT EXISTS idx_backup_sincronie_b ON backup_sincronie (guild_b);
