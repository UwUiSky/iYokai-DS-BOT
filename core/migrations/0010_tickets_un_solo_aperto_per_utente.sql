-- M 6.4 (issue #62): un utente può avere un solo ticket aperto per
-- server. Il controllo fatto nel codice non bastava: con due clic
-- insieme passavano entrambi. Ora lo garantisce il database.

-- Prima si sistemano i doppioni già presenti, altrimenti l'indice non
-- si può creare. Per ogni utente resta aperto il ticket più recente;
-- gli altri vengono chiusi (senza un "chiuso da": non è stato un
-- operatore). I loro canali restano: lo staff li elimina con
-- /ticket forceclose, che funziona anche su un ticket già chiuso.
UPDATE tickets AS vecchio
SET status = 'closed', closed_at = now()
WHERE vecchio.status = 'open'
  AND EXISTS (
      SELECT 1 FROM tickets AS recente
      WHERE recente.guild_id = vecchio.guild_id
        AND recente.user_id = vecchio.user_id
        AND recente.status = 'open'
        AND recente.ticket_number > vecchio.ticket_number
  );

CREATE UNIQUE INDEX IF NOT EXISTS uq_tickets_un_aperto_per_utente
    ON tickets (guild_id, user_id)
    WHERE status = 'open';
