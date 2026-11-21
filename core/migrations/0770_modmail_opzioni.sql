-- TKT-082, TKT-083, TKT-084 (#120): opzioni del ModMail per server.
-- anonimo_predefinito: le risposte dello staff non mostrano il nome (come «anonimo» di /ticket rispondi).
-- inoltra_tutto: ogni messaggio dello staff nel canale arriva all'utente (// all'inizio = nota interna).
-- conferma_invio: con un solo server l'utente conferma prima che il messaggio parta.
ALTER TABLE modmail_config ADD COLUMN IF NOT EXISTS anonimo_predefinito BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE modmail_config ADD COLUMN IF NOT EXISTS inoltra_tutto BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE modmail_config ADD COLUMN IF NOT EXISTS conferma_invio BOOLEAN NOT NULL DEFAULT TRUE;
