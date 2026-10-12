-- M 14.11 (PERF-3, GDPR-3): le tabelle che crescono si puliscono per data, quindi
-- serve un indice sulla colonna della data; `event_log.id` passa a BIGINT
-- (la sequenza SERIAL si fermerebbe a 2,1 miliardi di righe).
ALTER TABLE event_log ALTER COLUMN id TYPE BIGINT;

CREATE INDEX IF NOT EXISTS idx_automod_action_log_created_at ON automod_action_log (created_at);
CREATE INDEX IF NOT EXISTS idx_security_action_log_created_at ON security_action_log (created_at);
CREATE INDEX IF NOT EXISTS idx_verify_attempts_attempted_at ON verify_attempts (attempted_at);
CREATE INDEX IF NOT EXISTS idx_spam_trap_incidents_created_at ON spam_trap_incidents (created_at);
CREATE INDEX IF NOT EXISTS idx_guild_config_history_created_at ON guild_config_history (created_at);
CREATE INDEX IF NOT EXISTS idx_clan_treasury_ledger_created_at ON clan_treasury_ledger (created_at);
CREATE INDEX IF NOT EXISTS idx_guild_chest_ledger_created_at ON guild_chest_ledger (created_at);
CREATE INDEX IF NOT EXISTS idx_scheduled_actions_executed_at ON scheduled_actions (executed_at) WHERE executed = TRUE;
CREATE INDEX IF NOT EXISTS idx_spam_trap_join_invites_joined_at ON spam_trap_join_invites (joined_at);
