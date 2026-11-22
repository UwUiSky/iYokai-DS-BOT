-- BKP-028, #121: sincronia dei messaggi tra due canali (una riga per direzione: canale d'origine -> webhook del canale di arrivo).
CREATE TABLE IF NOT EXISTS backup_sincronia_canali (
    canale_da    BIGINT PRIMARY KEY,
    guild_da     BIGINT NOT NULL,
    canale_a     BIGINT NOT NULL,
    guild_a      BIGINT NOT NULL,
    webhook_url  TEXT NOT NULL,
    created_by   BIGINT NOT NULL,
    creato_il    TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (canale_da <> canale_a)
);
CREATE INDEX IF NOT EXISTS idx_backup_sincronia_canali_guild_da ON backup_sincronia_canali (guild_da);
CREATE INDEX IF NOT EXISTS idx_backup_sincronia_canali_guild_a ON backup_sincronia_canali (guild_a);
