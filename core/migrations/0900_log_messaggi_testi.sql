-- LOG-029 (D122): testo dei messaggi dei canali registrati, SOLO cifrato (AES-256-GCM, chiave nel .env, mai qui).
-- Finestra a scorrimento di 7 giorni (pulizia dal registro dei dati). In chiaro restano solo server, canale, messaggio,
-- autore, tipo di evento e momento.
CREATE TABLE IF NOT EXISTS log_messaggi_testi (
    id          BIGSERIAL PRIMARY KEY,
    guild_id    BIGINT NOT NULL,
    channel_id  BIGINT NOT NULL,
    message_id  BIGINT NOT NULL,
    user_id     BIGINT NOT NULL,
    evento      TEXT   NOT NULL CHECK (evento IN ('creato', 'modificato', 'cancellato')),
    cifrato     TEXT   NOT NULL,
    creato      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_log_messaggi_testi_utente ON log_messaggi_testi (guild_id, user_id, creato);
CREATE INDEX IF NOT EXISTS idx_log_messaggi_testi_creato ON log_messaggi_testi (creato);
