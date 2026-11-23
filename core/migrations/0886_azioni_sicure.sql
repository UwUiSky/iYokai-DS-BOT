-- UTL-024 e UTL-111 (D121): azioni sicure dei tag (fino a 3 per tag) e azioni programmate (fino a 5 per server).
CREATE TABLE IF NOT EXISTS tag_azioni (
    guild_id BIGINT NOT NULL,
    name     TEXT NOT NULL,
    pos      SMALLINT NOT NULL CHECK (pos BETWEEN 1 AND 3),
    azione   JSONB NOT NULL,
    PRIMARY KEY (guild_id, name, pos),
    FOREIGN KEY (guild_id, name) REFERENCES custom_commands (guild_id, name) ON DELETE CASCADE ON UPDATE CASCADE
);

CREATE TABLE IF NOT EXISTS azioni_programmate (
    id        BIGSERIAL PRIMARY KEY,
    guild_id  BIGINT NOT NULL,
    user_id   BIGINT NOT NULL,
    azione    JSONB  NOT NULL,
    quando    TIMESTAMPTZ NOT NULL,
    creato_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS azioni_programmate_server ON azioni_programmate (guild_id, quando);
