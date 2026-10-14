-- Risposte standard: di chi era la richiesta da cui sono nate (esportazione e cancellazione dei dati, GDPR).
ALTER TABLE ticket_standard_replies ADD COLUMN IF NOT EXISTS user_id BIGINT;
CREATE INDEX IF NOT EXISTS idx_ticket_standard_user ON ticket_standard_replies (user_id) WHERE user_id IS NOT NULL;
