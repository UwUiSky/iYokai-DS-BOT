-- r1doc (LIV-061): la classifica della settimana pubblicata da sola in un canale, una volta a settimana.
CREATE TABLE IF NOT EXISTS top_settimanale_conf (
    guild_id            BIGINT PRIMARY KEY,
    channel_id          BIGINT NOT NULL,
    ultima_annunciata   TEXT
);
