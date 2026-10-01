-- BUG-8: un'azione pianificata senza handler registrato viene segnata
-- come fallita (con il motivo) invece di restare "da eseguire" e
-- ripresentarsi ad ogni giro dello scheduler.
ALTER TABLE scheduled_actions ADD COLUMN IF NOT EXISTS failed_reason TEXT;
