-- NF-06 (#77): lingua personale di un utente (italiano o inglese).
-- Dato personale: una riga per utente, cancellata con la richiesta di cancellazione
-- (core/data_registry.py) ed esportata nell'art. 15. Nessuna scadenza: è una preferenza.
CREATE TABLE IF NOT EXISTS user_language (
    user_id    BIGINT PRIMARY KEY,
    language   TEXT NOT NULL CHECK (language IN ('it', 'en')),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
