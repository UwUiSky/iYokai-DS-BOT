-- AMD-026/027 (#58, #116): inviti da lasciar passare nella regola anti-invito.
ALTER TABLE automod_config ADD COLUMN IF NOT EXISTS invite_allowed JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE automod_config ADD COLUMN IF NOT EXISTS invite_own BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE automod_last_synced ADD COLUMN IF NOT EXISTS allow_list JSONB NOT NULL DEFAULT '[]'::jsonb;
