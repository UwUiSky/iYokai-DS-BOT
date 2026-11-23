-- D59 (CFG-040, CFG-041): livelli Gratuito, Premium, Ultra, VIP; concessioni, limiti per livello, prezzi e sconti.
ALTER TABLE livelli_funzione DROP CONSTRAINT IF EXISTS livelli_funzione_livello_check;
UPDATE livelli_funzione SET livello = 'ultra' WHERE livello = 'vip5';
UPDATE livelli_funzione SET livello = 'vip' WHERE livello = 'vip20';
ALTER TABLE livelli_funzione ADD CONSTRAINT livelli_funzione_livello_check CHECK (livello IN ('premium', 'ultra', 'vip'));

-- Chi ha quale livello e perché. scade_il NULL = a vita. Una riga per (soggetto, fonte, riferimento).
CREATE TABLE IF NOT EXISTS piani_concessioni (
    id          BIGSERIAL PRIMARY KEY,
    soggetto    TEXT NOT NULL CHECK (soggetto IN ('utente', 'server')),
    soggetto_id BIGINT NOT NULL,
    livello     TEXT NOT NULL CHECK (livello IN ('premium', 'ultra', 'vip')),
    fonte       TEXT NOT NULL CHECK (fonte IN ('mensile', 'annuale', 'a_vita', 'boost', 'patreon', 'manuale')),
    riferimento TEXT NOT NULL DEFAULT '',
    scade_il    TIMESTAMPTZ,
    concesso_da BIGINT,
    creato_il   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (soggetto, soggetto_id, fonte, riferimento)
);
CREATE INDEX IF NOT EXISTS idx_piani_concessioni_soggetto ON piani_concessioni (soggetto, soggetto_id);

-- Limiti numerici scelti dall'owner: senza riga vale il valore predefinito del codice.
CREATE TABLE IF NOT EXISTS piani_limiti (
    chiave  TEXT NOT NULL,
    livello TEXT NOT NULL CHECK (livello IN ('gratuito', 'premium', 'ultra', 'vip')),
    valore  INTEGER NOT NULL CHECK (valore BETWEEN 0 AND 1000000),
    PRIMARY KEY (chiave, livello)
);

-- Prezzi (in centesimi) scelti dall'owner. Nessun prezzo nel codice; il bot li mostra e basta.
CREATE TABLE IF NOT EXISTS piani_prezzi (
    livello  TEXT NOT NULL CHECK (livello IN ('premium', 'ultra', 'vip')),
    periodo  TEXT NOT NULL CHECK (periodo IN ('mensile', 'annuale', 'a_vita')),
    centesimi INTEGER NOT NULL CHECK (centesimi BETWEEN 0 AND 100000000),
    PRIMARY KEY (livello, periodo)
);

CREATE TABLE IF NOT EXISTS piani_sconti (
    nome        TEXT PRIMARY KEY CHECK (char_length(nome) BETWEEN 1 AND 40),
    percento    INTEGER NOT NULL CHECK (percento BETWEEN 1 AND 100),
    livello     TEXT CHECK (livello IS NULL OR livello IN ('premium', 'ultra', 'vip')),
    periodo     TEXT CHECK (periodo IS NULL OR periodo IN ('mensile', 'annuale', 'a_vita')),
    valido_fino TIMESTAMPTZ
);
