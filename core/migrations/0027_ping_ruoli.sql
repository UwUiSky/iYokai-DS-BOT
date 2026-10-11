-- #66 (10.6, D12): i ping di ruolo nei messaggi dell'admin funzionano solo
-- se chi ha configurato il messaggio aveva "Menziona tutti". Il permesso si
-- controlla al salvataggio e si ricorda qui. Nessun dato personale.
ALTER TABLE sticky_messages
    ADD COLUMN IF NOT EXISTS ping_ruoli BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE greetings_config
    ADD COLUMN IF NOT EXISTS welcome_ping_ruoli BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS goodbye_ping_ruoli BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS boost_ping_ruoli   BOOLEAN NOT NULL DEFAULT FALSE;
