-- Quali server hanno segnalato un'immagine trappola (una riga per server): senza file e senza utenti.
-- owner_id NULL = server troppo piccolo (meno di 25 membri): segnala per se', non conta per la soglia.
CREATE TABLE IF NOT EXISTS immagini_trappola_segnalazioni (
    sha256    BYTEA NOT NULL REFERENCES immagini_trappola(sha256) ON DELETE CASCADE,
    guild_id  BIGINT NOT NULL,
    owner_id  BIGINT,
    creata_il TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (sha256, guild_id)
);
CREATE INDEX IF NOT EXISTS idx_immagini_segnalazioni_guild ON immagini_trappola_segnalazioni (guild_id);
