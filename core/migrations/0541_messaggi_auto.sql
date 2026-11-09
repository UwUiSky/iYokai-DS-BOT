-- D69 B3: automatismi sui messaggi per server: citazione dei link ai messaggi, correzione dei link
-- (elenco «dominio>sostituto» scelto dall'admin) e canali annunci da pubblicare da soli (massimo 25).
CREATE TABLE IF NOT EXISTS messaggi_auto (
    guild_id        BIGINT PRIMARY KEY,
    citazioni       BOOLEAN NOT NULL DEFAULT FALSE,
    correzioni      TEXT[] NOT NULL DEFAULT '{}',
    pubblica_canali BIGINT[] NOT NULL DEFAULT '{}'
);
