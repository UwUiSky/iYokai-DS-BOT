-- Blocco A, voce 7: il token di iYokai Desktop scade (90 giorni dalla creazione). Quelli già emessi partono da oggi.
ALTER TABLE desktop_tokens ADD COLUMN IF NOT EXISTS scade_il TIMESTAMPTZ NOT NULL DEFAULT now() + interval '90 days';
