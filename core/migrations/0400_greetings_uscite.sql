-- D37: messaggi di ban e di addio. Il server sceglie quali escono e la grafica di ciascuno.
ALTER TABLE greetings_config ADD COLUMN IF NOT EXISTS leave_mode TEXT NOT NULL DEFAULT 'entrambi';

-- Una grafica (immagine o gif) per tipo: un link https oppure il file caricato (sotto 3 MB).
CREATE TABLE IF NOT EXISTS greetings_graphics (
    guild_id   BIGINT NOT NULL,
    kind       TEXT NOT NULL CHECK (kind IN ('ban', 'addio')),
    url        TEXT,
    image      BYTEA,
    filename   TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (guild_id, kind)
);
