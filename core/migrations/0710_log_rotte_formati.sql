-- LOG-016 e LOG-026 (#119): un canale per ogni evento di log (al posto di quello del gruppo) e un testo
-- scritto dal server per ogni evento. Una riga per (server, interruttore): al massimo 25 righe per server.
-- Nessun dato personale.
CREATE TABLE IF NOT EXISTS log_rotte (
    guild_id     BIGINT NOT NULL,
    interruttore TEXT   NOT NULL CHECK (char_length(interruttore) <= 32),
    channel_id   BIGINT NOT NULL,
    PRIMARY KEY (guild_id, interruttore)
);

CREATE TABLE IF NOT EXISTS log_formati (
    guild_id     BIGINT NOT NULL,
    interruttore TEXT   NOT NULL CHECK (char_length(interruttore) <= 32),
    testo        TEXT   NOT NULL CHECK (char_length(testo) BETWEEN 1 AND 300),
    formato_data TEXT   NOT NULL DEFAULT 'f' CHECK (formato_data IN ('f', 'F', 'd', 'D', 't', 'T', 'R')),
    PRIMARY KEY (guild_id, interruttore)
);
