-- D69 B2: cache delle città cercate con Nominatim (obbligatoria dai loro termini) e interruttore per server
-- dell'accorciatore di link (spento di base).
CREATE TABLE IF NOT EXISTS web_luoghi_cache (
    testo     TEXT PRIMARY KEY,
    lat       DOUBLE PRECISION NOT NULL,
    lon       DOUBLE PRECISION NOT NULL,
    nome      TEXT NOT NULL,
    creato_il TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS web_impostazioni (
    guild_id        BIGINT PRIMARY KEY,
    accorcia_attivo BOOLEAN NOT NULL DEFAULT FALSE
);
