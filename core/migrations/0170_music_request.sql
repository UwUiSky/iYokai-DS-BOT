-- NF-19 (#90): canale delle richieste musicali, uno per server.
-- message_id = messaggio "player" con i bottoni; voice_channel_id = sessione
-- (canale vocale) mostrata dal player, l'ultima usata dal canale.
CREATE TABLE IF NOT EXISTS music_request_channels (
    guild_id          BIGINT PRIMARY KEY,
    channel_id        BIGINT NOT NULL,
    message_id        BIGINT,
    voice_channel_id  BIGINT,
    set_by            BIGINT NOT NULL,
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
