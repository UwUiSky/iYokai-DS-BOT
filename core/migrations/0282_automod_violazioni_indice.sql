-- AMD-062 (#116): /automod violazioni legge le righe di un utente in un server.
CREATE INDEX IF NOT EXISTS idx_automod_action_log_utente
    ON automod_action_log (guild_id, user_id, created_at DESC);
