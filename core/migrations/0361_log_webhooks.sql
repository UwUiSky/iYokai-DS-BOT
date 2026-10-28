-- #113: canali di log via webhook (D33). Un webhook per canale; il token è cifrato a riposo
-- (OAUTH_ENCRYPTION_KEY) e si cancella con il server (core/data_registry.py).
CREATE TABLE IF NOT EXISTS log_webhooks (
    guild_id        BIGINT NOT NULL,
    channel_id      BIGINT NOT NULL,
    webhook_id      BIGINT NOT NULL,
    encrypted_token TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (guild_id, channel_id)
);
