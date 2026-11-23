-- ECO-006 (D121): canale con il registro dei movimenti di monete, a lotti. `ultimo_id` = ultimo movimento già raccontato.
CREATE TABLE IF NOT EXISTS economia_registro_conf (
    guild_id    BIGINT PRIMARY KEY,
    channel_id  BIGINT NOT NULL,
    ultimo_id   BIGINT NOT NULL DEFAULT 0
);
