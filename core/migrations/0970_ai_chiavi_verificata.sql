-- #122: una chiave AI propria dà il livello VIP solo se il servizio l'ha accettata. Le righe già presenti non sono
-- mai state provate: partono come non verificate e vanno rimesse.
ALTER TABLE ai_chiavi_proprie ADD COLUMN IF NOT EXISTS verificata BOOLEAN NOT NULL DEFAULT false;
