-- Catalogo #115 (MOD-051): gli ultimi messaggi del canale al momento di un caso (warn, timeout, kick, ban), per 30 giorni.
CREATE TABLE IF NOT EXISTS moderation_chat_log (
    guild_id     BIGINT NOT NULL,
    case_number  INTEGER NOT NULL,
    channel_id   BIGINT NOT NULL,
    messaggi     INTEGER NOT NULL,
    contenuto    BYTEA   NOT NULL,
    creato       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (guild_id, case_number)
);
