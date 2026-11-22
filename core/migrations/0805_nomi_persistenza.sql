-- Catalogo #115 (MOD-103, MOD-104): storico dei nomi (scade dopo 90 giorni) e soprannome / mute vocale da ridare a chi rientra.
CREATE TABLE IF NOT EXISTS moderation_nomi (
    id        BIGSERIAL PRIMARY KEY,
    guild_id  BIGINT NOT NULL,
    user_id   BIGINT NOT NULL,
    tipo      TEXT   NOT NULL,        -- soprannome | nome | visualizzato
    prima     TEXT,
    dopo      TEXT,
    quando    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_moderation_nomi_utente ON moderation_nomi (guild_id, user_id, quando DESC);
CREATE TABLE IF NOT EXISTS moderation_persistenza (
    guild_id  BIGINT NOT NULL,
    user_id   BIGINT NOT NULL,
    nick      TEXT,
    mute      BOOLEAN NOT NULL DEFAULT FALSE,
    deaf      BOOLEAN NOT NULL DEFAULT FALSE,
    quando    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (guild_id, user_id)
);
