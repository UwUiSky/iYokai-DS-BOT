-- #125 B16 (ECO-007, 161): storico personale dei movimenti di monete e tetto vocale giornaliero scelto dal server.
ALTER TABLE leveling_settings ADD COLUMN IF NOT EXISTS voce_max_minuti INTEGER NOT NULL DEFAULT 360;

CREATE TABLE IF NOT EXISTS economia_movimenti (
    id       BIGSERIAL PRIMARY KEY,
    guild_id BIGINT  NOT NULL,
    user_id  BIGINT  NOT NULL,
    delta    BIGINT  NOT NULL,
    motivo   TEXT    NOT NULL,
    at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS economia_movimenti_utente ON economia_movimenti (guild_id, user_id, id DESC);
