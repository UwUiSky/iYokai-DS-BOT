-- D39 (28/10/2026, owner): una variante segnalata da abbastanza proprietari diventa «condivisa»
-- (vale in tutti i server, ma la giudica sempre l'AI); solo l'owner la rende «approvata» (certa).
ALTER TABLE odio_parole DROP CONSTRAINT IF EXISTS odio_parole_stato_check;
ALTER TABLE odio_parole ADD CONSTRAINT odio_parole_stato_check
    CHECK (stato IN ('base', 'candidata', 'condivisa', 'approvata', 'rifiutata'));
-- Le varianti già approvate in automatico (nessuna approvazione dell'owner registrata) tornano condivise
-- non è distinguibile qui: restano come sono, l'owner le rivede con /automod odio libreria elenca.
