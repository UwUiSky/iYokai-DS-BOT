-- AI-R-038 (r12): chi vuole può permettere agli altri di chiedere un messaggio «nel suo stile». Di partenza no.
ALTER TABLE ai_utenti ADD COLUMN IF NOT EXISTS stile_consentito BOOLEAN NOT NULL DEFAULT FALSE;
