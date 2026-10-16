-- LOG-017 (#119): gli interruttori dei singoli eventi di log spenti in un
-- server. Nessuna riga = tutto acceso (come prima).
CREATE TABLE IF NOT EXISTS log_eventi_spenti (
    guild_id     BIGINT NOT NULL,
    interruttore TEXT   NOT NULL CHECK (char_length(interruttore) <= 32),
    PRIMARY KEY (guild_id, interruttore)
);
