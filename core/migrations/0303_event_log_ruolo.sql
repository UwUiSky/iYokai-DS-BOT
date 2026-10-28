-- 8.17: /log cerca ruolo legge event_log per server e ruolo. Indice parziale:
-- solo le righe con un ruolo (creazione, modifica, cancellazione di un ruolo),
-- così le altre scritture sulla tabella non pagano nulla.
CREATE INDEX IF NOT EXISTS idx_event_log_guild_role_tempo
    ON event_log (guild_id, role_id, created_at DESC) WHERE role_id IS NOT NULL;
