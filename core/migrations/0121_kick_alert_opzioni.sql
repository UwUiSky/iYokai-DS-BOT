-- NF-32 (#103) e #129: avvisi Kick, ruolo "in diretta", opzioni per sottoscrizione.
CREATE TABLE IF NOT EXISTS kick_subscriptions (
    id                       SERIAL PRIMARY KEY,
    guild_id                 BIGINT NOT NULL,
    channel_id               BIGINT NOT NULL,
    kick_slug                TEXT NOT NULL,
    label                    TEXT NOT NULL,
    live_message_template    TEXT NOT NULL,
    offline_message_template TEXT NOT NULL,
    last_known_live          BOOLEAN NOT NULL DEFAULT false,
    created_by               BIGINT NOT NULL,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_kick_subscriptions_guild ON kick_subscriptions (guild_id);

-- Opzioni facoltative di una sottoscrizione (kind: RSS, TW, YT, KK). Senza riga valgono i valori predefiniti.
CREATE TABLE IF NOT EXISTS alert_options (
    kind            TEXT NOT NULL,
    sub_id          INTEGER NOT NULL,
    guild_id        BIGINT NOT NULL,
    mention_role_id BIGINT,
    ping_allowed    BOOLEAN NOT NULL DEFAULT false,
    notify_end      BOOLEAN NOT NULL DEFAULT true,
    delete_on_end   BOOLEAN NOT NULL DEFAULT false,
    watch_button    BOOLEAN NOT NULL DEFAULT true,
    crosspost       BOOLEAN NOT NULL DEFAULT false,
    live_member_id  BIGINT,
    last_message_id BIGINT,
    PRIMARY KEY (kind, sub_id)
);
CREATE INDEX IF NOT EXISTS idx_alert_options_guild ON alert_options (guild_id);

CREATE TABLE IF NOT EXISTS live_role_settings (
    guild_id BIGINT PRIMARY KEY,
    role_id  BIGINT NOT NULL
);
