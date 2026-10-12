-- NF-04 (#46, #37): correzioni del secondo giro.
-- 1) ban e kick dell'automod (`automod_escalation`) e il mute con ruolo (`mute_role`)
--    restano nello storico come gli altri: una richiesta di cancellazione non li toglie.
--    La colonna è calcolata, quindi si rifà; tests/test_data_registry.py controlla che
--    ogni action_type scritto dai cog sia dichiarato qui o come non trattenuto.
ALTER TABLE moderation_cases DROP COLUMN IF EXISTS retain_for_security;
ALTER TABLE moderation_cases
    ADD COLUMN retain_for_security BOOLEAN
    GENERATED ALWAYS AS (action_type IN (
        'ban', 'tempban', 'softban', 'kick', 'spam_trap_ban', 'automod_escalation', 'mute_role'
    )) STORED;

-- 2) Chi chiede la cancellazione passa a user_id = 0 nei ticket: più persone con un ticket
--    aperto nello stesso server finirebbero tutte su (guild, 0) e l'indice unico rifiuterebbe
--    la seconda. L'indice vale solo per utenti veri (stesso nome: ticket_repo lo riconosce).
DROP INDEX IF EXISTS uq_tickets_un_aperto_per_utente;
CREATE UNIQUE INDEX uq_tickets_un_aperto_per_utente
    ON tickets (guild_id, user_id)
    WHERE status = 'open' AND user_id <> 0;
