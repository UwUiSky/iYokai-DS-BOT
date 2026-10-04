-- BUG-27: un'azione senza handler o con un handler che solleva non
-- diventa più "failed" al primo colpo. `attempts` conta i tentativi
-- falliti; `next_attempt_at` dice quando riprovare (NULL = mai fallita,
-- vale execute_at, che resta la scadenza originale).
ALTER TABLE scheduled_actions ADD COLUMN IF NOT EXISTS attempts INT NOT NULL DEFAULT 0;
ALTER TABLE scheduled_actions ADD COLUMN IF NOT EXISTS next_attempt_at TIMESTAMPTZ;
