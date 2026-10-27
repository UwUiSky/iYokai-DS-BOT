-- Motore AI (#95, SPEC §25.20, §25.23): interruttore di manutenzione globale dell'owner
-- e inizio del periodo di prova dell'AI per server (una sola volta).
CREATE TABLE IF NOT EXISTS ai_globale (
    chiave        TEXT PRIMARY KEY CHECK (chiave IN ('manutenzione')),
    valore        TEXT NOT NULL DEFAULT '',
    aggiornato_da BIGINT,
    aggiornato_il TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE ai_config ADD COLUMN IF NOT EXISTS prova_inizio TIMESTAMPTZ;
