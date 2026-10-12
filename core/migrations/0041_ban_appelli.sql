-- Appelli contro i ban manuali (NF-30, issue #101).
CREATE TABLE IF NOT EXISTS ban_appelli (
    id              SERIAL PRIMARY KEY,
    guild_id        BIGINT NOT NULL,
    user_id         BIGINT NOT NULL,
    case_number     INTEGER,
    testo           TEXT NOT NULL,
    stato           TEXT NOT NULL DEFAULT 'aperto',
    creato_il       TIMESTAMPTZ NOT NULL DEFAULT now(),
    deciso_da       BIGINT,
    deciso_il       TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_ban_appelli_utente ON ban_appelli (guild_id, user_id, creato_il DESC);
