-- D69 B15: traguardi del conteggio (un numero preciso, oppure ogni tanti numeri: ruolo e/o messaggio) e avvisi
-- richiesti dai membri («scrivimi quando si arriva a N»). Max 25 traguardi per canale e 5 avvisi per membro.
CREATE TABLE IF NOT EXISTS conteggio_traguardi (
    id         BIGSERIAL PRIMARY KEY,
    guild_id   BIGINT NOT NULL,
    channel_id BIGINT NOT NULL,
    numero     INT CHECK (numero > 0),
    ogni       INT CHECK (ogni > 0),
    ruolo_id   BIGINT,
    messaggio  TEXT CHECK (char_length(messaggio) <= 300),
    CHECK ((numero IS NULL) <> (ogni IS NULL)),
    CHECK (ruolo_id IS NOT NULL OR messaggio IS NOT NULL)
);
CREATE INDEX IF NOT EXISTS idx_conteggio_traguardi_canale ON conteggio_traguardi (guild_id, channel_id);

CREATE TABLE IF NOT EXISTS conteggio_avvisi (
    guild_id   BIGINT NOT NULL,
    channel_id BIGINT NOT NULL,
    user_id    BIGINT NOT NULL,
    numero     INT NOT NULL CHECK (numero > 0),
    PRIMARY KEY (guild_id, channel_id, user_id, numero)
);
CREATE INDEX IF NOT EXISTS idx_conteggio_avvisi_utente ON conteggio_avvisi (user_id);
