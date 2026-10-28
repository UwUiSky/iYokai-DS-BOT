-- Libreria delle parole d'odio (D35): una candidata diventa globale con 3 PROPRIETARI diversi,
-- non con 3 server dello stesso proprietario. NULL = server troppo piccolo: non conta.
ALTER TABLE odio_segnalazioni ADD COLUMN IF NOT EXISTS owner_id BIGINT;
