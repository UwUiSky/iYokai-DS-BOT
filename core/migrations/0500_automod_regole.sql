-- D63: regole AutoMod (filtri e regole personali) con condizioni, azioni e contatore; liste con nome.
CREATE TABLE IF NOT EXISTS automod_regole (
    id            BIGSERIAL PRIMARY KEY,
    guild_id      BIGINT NOT NULL,
    chiave        TEXT NOT NULL,
    tipo          TEXT NOT NULL CHECK (tipo IN ('filtro', 'personale')),
    nome          TEXT NOT NULL,
    evento        TEXT NOT NULL DEFAULT 'messaggio',
    attiva        BOOLEAN NOT NULL DEFAULT TRUE,
    gruppo        TEXT,
    innesco       JSONB NOT NULL DEFAULT '{}'::jsonb,
    condizioni    JSONB NOT NULL DEFAULT '{}'::jsonb,
    azioni        JSONB NOT NULL DEFAULT '[]'::jsonb,
    contatore     JSONB,
    calore        SMALLINT NOT NULL DEFAULT 0 CHECK (calore BETWEEN 0 AND 100),
    aggiornata_da BIGINT,
    aggiornata_il TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (guild_id, chiave)
);
CREATE INDEX IF NOT EXISTS idx_automod_regole_gruppo ON automod_regole (guild_id, gruppo) WHERE gruppo IS NOT NULL;

CREATE TABLE IF NOT EXISTS automod_liste (
    id        BIGSERIAL PRIMARY KEY,
    guild_id  BIGINT NOT NULL,
    nome      TEXT NOT NULL,
    tipo      TEXT NOT NULL CHECK (tipo IN ('parole', 'domini')),
    voci      TEXT[] NOT NULL DEFAULT '{}',
    UNIQUE (guild_id, nome)
);
