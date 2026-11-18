-- #129 (ALR-008): avvisi per le dirette su Picarto. Stesso schema di kick_subscriptions.
CREATE TABLE IF NOT EXISTS picarto_subscriptions (
    id                       SERIAL PRIMARY KEY,
    guild_id                 BIGINT NOT NULL,
    channel_id               BIGINT NOT NULL,
    picarto_name             TEXT NOT NULL,
    label                    TEXT NOT NULL,
    live_message_template    TEXT NOT NULL,
    offline_message_template TEXT NOT NULL,
    last_known_live          BOOLEAN NOT NULL DEFAULT false,
    created_by               BIGINT NOT NULL,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_picarto_subscriptions_guild ON picarto_subscriptions (guild_id);
