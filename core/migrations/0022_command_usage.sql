-- F9 (#147): ultimo comando usato da ogni utente in ogni server, per il
-- pannello di -cerca-comando. Una riga per (server, utente); guild_id = 0 in DM.
-- DATO PERSONALE: conservato al massimo 90 giorni e al massimo 200.000 righe
-- (pulizia in core/repositories/command_usage_repo.py). La cancellazione per
-- utente/server sarà collegata da F5 (core/data_registry.py, forget_user_service).
CREATE TABLE IF NOT EXISTS command_usage (
    guild_id     BIGINT NOT NULL,
    user_id      BIGINT NOT NULL,
    command_path TEXT NOT NULL,
    used_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (guild_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_command_usage_used_at ON command_usage (used_at);
CREATE INDEX IF NOT EXISTS idx_command_usage_user ON command_usage (user_id);
