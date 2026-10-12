-- Ban temporaneo con rientro (issue #138): l'utente aveva autorizzato il
-- ripristino utenti, quindi alla scadenza può rientrare da solo (OAuth).
ALTER TABLE tempban_stato ADD COLUMN IF NOT EXISTS oauth_rientro BOOLEAN NOT NULL DEFAULT FALSE;
