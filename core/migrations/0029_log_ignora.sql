-- #73 (NF-02): cosa il log dei messaggi deve ignorare (canali, utenti,
-- prefissi del testo). `valore` e un id per canale/utente, il prefisso
-- per `prefisso`. Nessun contenuto di messaggi.
CREATE TABLE IF NOT EXISTS log_ignora (
    guild_id BIGINT NOT NULL,
    genere   TEXT   NOT NULL CHECK (genere IN ('canale', 'utente', 'prefisso')),
    valore   TEXT   NOT NULL,
    PRIMARY KEY (guild_id, genere, valore)
);
