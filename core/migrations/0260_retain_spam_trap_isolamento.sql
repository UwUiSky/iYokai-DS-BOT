-- D6: anche i kick dello spam-trap e i ban in isolamento (#138) sono azioni di sicurezza:
-- restano nello storico quando un utente chiede la cancellazione dei suoi dati.
-- Il timeout dello spam-trap no, come gli altri timeout.
ALTER TABLE moderation_cases DROP COLUMN IF EXISTS retain_for_security;
ALTER TABLE moderation_cases
    ADD COLUMN retain_for_security BOOLEAN
    GENERATED ALWAYS AS (action_type IN (
        'ban', 'tempban', 'softban', 'kick', 'spam_trap_ban', 'spam_trap_kick', 'isolamento',
        'automod_escalation', 'mute_role'
    )) STORED;
