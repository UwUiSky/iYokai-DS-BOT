-- #131 B11 (D70): ruoli che possono o non possono usare un suono (`/admin-musica suono-ruoli`, massimo 20 per
-- suono, tetto nel codice) e voti settimanali di «Smash or pass» (`/giochi smash`, un voto a testa per personaggio).
CREATE TABLE IF NOT EXISTS suoni_ruoli (
    guild_id  BIGINT NOT NULL,
    suono     TEXT NOT NULL,
    ruolo_id  BIGINT NOT NULL,
    modo      TEXT NOT NULL CHECK (modo IN ('consenti', 'vieta')),
    PRIMARY KEY (guild_id, suono, ruolo_id)
);
CREATE TABLE IF NOT EXISTS smash_voti (
    guild_id    BIGINT NOT NULL,
    settimana   TEXT NOT NULL,
    personaggio TEXT NOT NULL,
    user_id     BIGINT NOT NULL,
    scelta      TEXT NOT NULL CHECK (scelta IN ('smash', 'pass')),
    creato_il   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (guild_id, settimana, personaggio, user_id)
);
