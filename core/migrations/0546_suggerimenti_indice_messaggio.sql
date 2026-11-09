-- D69 B7: i voti (reazioni) cercano il suggerimento dal messaggio: senza indice sarebbe una scansione a ogni reazione.
CREATE INDEX IF NOT EXISTS idx_suggestions_message ON suggestions (message_id) WHERE message_id IS NOT NULL;
