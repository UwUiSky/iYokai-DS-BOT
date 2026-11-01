-- AI-R-089 e AI-R-101 (r12): scelte dell'owner sopra il .env (modello, fascia e tipi per fornitore, tetto di lunghezza).
ALTER TABLE ai_globale DROP CONSTRAINT IF EXISTS ai_globale_chiave_check;
ALTER TABLE ai_globale ADD CONSTRAINT ai_globale_chiave_check CHECK (chiave IN ('manutenzione', 'override_ai', 'tetto_token'));
