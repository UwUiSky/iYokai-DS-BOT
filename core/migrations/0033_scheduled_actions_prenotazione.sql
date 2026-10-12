-- M 14.4 (LIM-47): lo scheduler non tiene più aperta una transazione mentre
-- l'azione parla con Discord. La riga si "prenota" (claimed_at = adesso), la
-- transazione si chiude, l'azione gira, poi si segna l'esito. Una prenotazione
-- più vecchia di 10 minuti (processo morto a metà) viene ripresa.
ALTER TABLE scheduled_actions ADD COLUMN IF NOT EXISTS claimed_at TIMESTAMPTZ;
