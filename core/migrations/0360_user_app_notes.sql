-- SPEC B.4 (NF-36, #107): note e liste personali di iYokai App. Dato personale: una riga per voce,
-- cancellata con la richiesta di cancellazione e esportata nell'art. 15 (core/data_registry.py).
-- `lista` vuota = le note; altrimenti il nome della lista.
CREATE TABLE IF NOT EXISTS user_app_notes (
    id         BIGSERIAL PRIMARY KEY,
    user_id    BIGINT NOT NULL,
    lista      TEXT NOT NULL DEFAULT '',
    testo      TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_user_app_notes_utente ON user_app_notes (user_id, lista, id);
