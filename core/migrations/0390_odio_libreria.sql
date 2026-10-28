-- Libreria mondiale delle parole d'odio e delle loro varianti (D35, r11).
-- Globale: non è di un server. Stati: base, candidata, approvata, rifiutata.
CREATE TABLE IF NOT EXISTS odio_parole (
    id          BIGSERIAL PRIMARY KEY,
    variante    TEXT NOT NULL UNIQUE,
    lingua      TEXT NOT NULL DEFAULT '',
    stato       TEXT NOT NULL DEFAULT 'candidata' CHECK (stato IN ('base', 'candidata', 'approvata', 'rifiutata')),
    creata_il   TIMESTAMPTZ NOT NULL DEFAULT now(),
    aggiornata_il TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Quali server hanno segnalato una variante (una riga per server): senza testi, senza utenti.
CREATE TABLE IF NOT EXISTS odio_segnalazioni (
    parola_id  BIGINT NOT NULL REFERENCES odio_parole(id) ON DELETE CASCADE,
    guild_id   BIGINT NOT NULL,
    creata_il  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (parola_id, guild_id)
);
CREATE INDEX IF NOT EXISTS idx_odio_segnalazioni_guild ON odio_segnalazioni (guild_id);
