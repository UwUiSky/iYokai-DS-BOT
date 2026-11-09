-- D69 B24: eventi con iscrizioni. Un evento, i suoi iscritti (si, forse, attesa). Gli eventi finiti restano 90 giorni.
CREATE TABLE IF NOT EXISTS eventi (
    id               BIGSERIAL PRIMARY KEY,
    guild_id         BIGINT NOT NULL,
    channel_id       BIGINT NOT NULL,
    message_id       BIGINT,
    autore_id        BIGINT NOT NULL,
    titolo           TEXT   NOT NULL,
    descrizione      TEXT   NOT NULL DEFAULT '',
    quando           TIMESTAMPTZ NOT NULL,
    posti            INT CHECK (posti IS NULL OR posti BETWEEN 1 AND 500),
    ruolo_ping_id    BIGINT,
    discord_event_id BIGINT,
    stato            TEXT   NOT NULL DEFAULT 'attivo' CHECK (stato IN ('attivo', 'annullato')),
    creato_il        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_eventi_server ON eventi (guild_id, quando);
CREATE INDEX IF NOT EXISTS idx_eventi_messaggio ON eventi (message_id) WHERE message_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS eventi_iscritti (
    evento_id BIGINT NOT NULL REFERENCES eventi (id) ON DELETE CASCADE,
    guild_id  BIGINT NOT NULL,
    user_id   BIGINT NOT NULL,
    stato     TEXT   NOT NULL CHECK (stato IN ('si', 'forse', 'attesa')),
    dal       TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (evento_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_eventi_iscritti_utente ON eventi_iscritti (user_id);
