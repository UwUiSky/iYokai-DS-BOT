-- #131 B6/B8 (D70): impostazioni del Divertimento per server (pacchetti delle carte, pacchetto «adulti» spento di base)
-- e regole del quiz.
CREATE TABLE IF NOT EXISTS fun_impostazioni (
    guild_id        BIGINT PRIMARY KEY,
    carte_pacchetti TEXT NOT NULL DEFAULT 'base,nerd,gamer',
    carte_adulti    BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE TABLE IF NOT EXISTS quiz_impostazioni (
    guild_id         BIGINT PRIMARY KEY,
    punti            INTEGER NOT NULL DEFAULT 10 CHECK (punti BETWEEN 1 AND 50),
    secondi          INTEGER NOT NULL DEFAULT 30 CHECK (secondi BETWEEN 10 AND 120),
    mostra_risposta  BOOLEAN NOT NULL DEFAULT TRUE,
    bot_gioca        BOOLEAN NOT NULL DEFAULT FALSE
);
