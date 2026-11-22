-- ALR-049 (#129): ruoli collegati di Discord per affiliati e partner Twitch.
-- Una riga per persona. I token (di Twitch e di Discord) stanno SOLO cifrati (AES-256-GCM, core/oauth_crypto).
CREATE TABLE IF NOT EXISTS ruoli_collegati_twitch (
    user_id            BIGINT      PRIMARY KEY,
    twitch_id          TEXT        NOT NULL CHECK (char_length(twitch_id) BETWEEN 1 AND 40),
    twitch_login       TEXT        NOT NULL CHECK (char_length(twitch_login) BETWEEN 1 AND 40),
    tipo               TEXT        NOT NULL DEFAULT '' CHECK (tipo IN ('', 'affiliate', 'partner')),
    twitch_token       TEXT        NOT NULL,
    twitch_refresh     TEXT,
    twitch_scade_il    TIMESTAMPTZ,
    discord_token      TEXT,
    discord_refresh    TEXT,
    discord_scade_il   TIMESTAMPTZ,
    collegato_il       TIMESTAMPTZ,
    creato_il          TIMESTAMPTZ NOT NULL DEFAULT now()
);
