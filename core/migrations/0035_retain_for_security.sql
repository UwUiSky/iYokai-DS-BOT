-- NF-04 (#46): ban e kick restano nello storico anche dopo i 90 giorni dall'uscita
-- del bot e dopo una richiesta di cancellazione (affidabilità al rientro).
-- Colonna calcolata: nessun cog deve ricordarsi di impostarla.
ALTER TABLE moderation_cases
    ADD COLUMN IF NOT EXISTS retain_for_security BOOLEAN
    GENERATED ALWAYS AS (action_type IN ('ban', 'tempban', 'softban', 'kick', 'spam_trap_ban')) STORED;
CREATE INDEX IF NOT EXISTS idx_moderation_cases_utente
    ON moderation_cases (user_id);
