-- #68 (giro correzioni): storico delle promozioni avvenute prima della 0070,
-- un solo main per server di backup, registro di chi è già stato contattato
-- dal restore.

-- Coppie promosse prima: il vecchio main aveva un job completato verso un
-- server che ora è a sua volta main.
INSERT INTO backup_pair_history (old_main_guild_id, promoted_guild_id)
SELECT DISTINCT j.main_guild_id, j.backup_guild_id
FROM backup_jobs j
JOIN backup_pairs p ON p.main_guild_id = j.backup_guild_id
WHERE j.status = 'completed' AND j.backup_guild_id IS NOT NULL
  AND j.main_guild_id <> j.backup_guild_id
ON CONFLICT DO NOTHING;

-- Prima dell'indice unico: se due coppie hanno lo stesso backup resta la più recente.
UPDATE backup_pairs a SET backup_guild_id = NULL
WHERE a.backup_guild_id IS NOT NULL AND EXISTS (
    SELECT 1 FROM backup_pairs b
    WHERE b.backup_guild_id = a.backup_guild_id
      AND (b.updated_at > a.updated_at
           OR (b.updated_at = a.updated_at AND b.main_guild_id > a.main_guild_id))
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_backup_pairs_backup_guild
    ON backup_pairs (backup_guild_id) WHERE backup_guild_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS restore_contacts (
    target_guild_id  BIGINT NOT NULL,
    source_guild_id  BIGINT NOT NULL,
    user_id          BIGINT NOT NULL,
    kind             TEXT NOT NULL,
    contacted_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (target_guild_id, source_guild_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_restore_contacts_data ON restore_contacts (contacted_at);
