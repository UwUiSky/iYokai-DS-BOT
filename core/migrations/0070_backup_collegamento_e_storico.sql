-- M 12.1 (#68): codice di collegamento tra server principale e server di backup.
-- Il codice in chiaro non si salva mai: solo l'impronta (SHA-256).
CREATE TABLE IF NOT EXISTS backup_link_codes (
    id              SERIAL PRIMARY KEY,
    main_guild_id   BIGINT NOT NULL,
    code_hash       TEXT NOT NULL UNIQUE,
    created_by      BIGINT NOT NULL,
    expires_at      TIMESTAMPTZ NOT NULL,
    used_at         TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_backup_link_codes_main
    ON backup_link_codes (main_guild_id, created_at);

-- M 12.13 (#68, BUG-34): dopo la promozione il vecchio main perde il backup
-- in backup_pairs; qui resta la coppia storica per /admin backup restore-utenti.
CREATE TABLE IF NOT EXISTS backup_pair_history (
    old_main_guild_id  BIGINT NOT NULL,
    promoted_guild_id  BIGINT NOT NULL,
    promoted_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (old_main_guild_id, promoted_guild_id)
);
