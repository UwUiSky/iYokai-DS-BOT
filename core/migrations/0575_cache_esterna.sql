-- #131 B9 (D70): cache comune delle risposte dei servizi esterni (schede di giochi, anime, carte...).
-- Si legge solo se `scade` è nel futuro; il lavoro giornaliero dei dati toglie le righe vecchie.
CREATE TABLE IF NOT EXISTS cache_esterna (
    chiave   TEXT PRIMARY KEY,
    risposta JSONB NOT NULL,
    scade    TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cache_esterna_scade ON cache_esterna (scade);
