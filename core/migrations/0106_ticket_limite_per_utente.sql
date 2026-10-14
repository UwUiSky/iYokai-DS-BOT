-- NF-13: il numero di ticket aperti per utente è configurabile (/gestione ticket limite, default 1).
-- L'indice unico ne ammetteva uno solo: il controllo passa a ticket_repo.create_ticket, che lo fa
-- dentro una transazione con un blocco per (server, utente), quindi regge anche due clic insieme.
DROP INDEX IF EXISTS uq_tickets_un_aperto_per_utente;
CREATE INDEX IF NOT EXISTS idx_tickets_aperti_per_utente
    ON tickets (guild_id, user_id) WHERE status = 'open';
