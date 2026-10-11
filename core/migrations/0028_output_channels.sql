-- #72 (NF-01): dove il bot scrive ogni tipo di log. Un canale di testo
-- oppure un forum (nel forum c'e un post per tipo). `avvisato` serve a
-- mandare l'allarme "canale non raggiungibile" una volta sola.
CREATE TABLE IF NOT EXISTS output_channels (
    guild_id   BIGINT  NOT NULL,
    tipo       TEXT    NOT NULL,
    channel_id BIGINT  NOT NULL,
    post_id    BIGINT,
    avvisato   BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (guild_id, tipo)
);
