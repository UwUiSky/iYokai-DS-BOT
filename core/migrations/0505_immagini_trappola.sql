-- Libreria mondiale delle immagini trappola (D62, come D39). Globale: nessun dato di utenti.
-- Stati: candidata (vale nei server che l'hanno segnalata), condivisa (3 proprietari diversi, vale ovunque),
-- approvata (owner del bot: certa), rifiutata (non vale mai).
CREATE TABLE IF NOT EXISTS immagini_trappola (
    sha256        BYTEA PRIMARY KEY CHECK (octet_length(sha256) = 32),
    dhash         BIGINT,
    stato         TEXT NOT NULL DEFAULT 'candidata' CHECK (stato IN ('candidata', 'condivisa', 'approvata', 'rifiutata')),
    motivo        TEXT NOT NULL DEFAULT '' CHECK (length(motivo) <= 200),
    creata_il     TIMESTAMPTZ NOT NULL DEFAULT now(),
    aggiornata_il TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_immagini_trappola_stato ON immagini_trappola (stato);
