-- #125 B9 (ECO-033, 034, 035, 036, 037, 038): monete per messaggio e stipendi per ruolo.
ALTER TABLE leveling_settings
    ADD COLUMN IF NOT EXISTS msg_coins        INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS msg_coins_pausa  INTEGER NOT NULL DEFAULT 60,
    ADD COLUMN IF NOT EXISTS msg_coins_tetto  INTEGER NOT NULL DEFAULT 200,
    ADD COLUMN IF NOT EXISTS stipendio_auto   BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS stipendio_ora    INTEGER NOT NULL DEFAULT 12;

CREATE TABLE IF NOT EXISTS economia_canali_monete (
    guild_id   BIGINT NOT NULL,
    channel_id BIGINT NOT NULL,
    PRIMARY KEY (guild_id, channel_id)
);

-- Monete da messaggi prese oggi: il tetto giornaliero sta nella stessa scrittura che le dà.
CREATE TABLE IF NOT EXISTS economia_msg_giorno (
    guild_id BIGINT NOT NULL,
    user_id  BIGINT NOT NULL,
    giorno   DATE   NOT NULL,
    totale   INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (guild_id, user_id, giorno)
);

-- Stipendio (importo positivo) o tassa (negativo) di un ruolo; in contanti o in banca.
CREATE TABLE IF NOT EXISTS economia_stipendi (
    guild_id BIGINT  NOT NULL,
    role_id  BIGINT  NOT NULL,
    importo  INTEGER NOT NULL CHECK (importo <> 0 AND importo BETWEEN -100000 AND 100000),
    in_banca BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (guild_id, role_id)
);

-- Il giro automatico di un giorno si fa una volta sola per server.
CREATE TABLE IF NOT EXISTS economia_stipendi_giro (
    guild_id BIGINT NOT NULL,
    giorno   DATE   NOT NULL,
    PRIMARY KEY (guild_id, giorno)
);
