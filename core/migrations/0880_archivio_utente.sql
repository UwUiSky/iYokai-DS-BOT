-- LOG-029 (D121): archivio degli eventi dei messaggi di un utente (ultimi 3 giorni), legato al caso. Resta finché esiste il caso.
CREATE TABLE IF NOT EXISTS moderation_archivio_utente (
    guild_id     BIGINT NOT NULL,
    case_number  INTEGER NOT NULL,
    user_id      BIGINT NOT NULL,
    eventi       INTEGER NOT NULL,
    contenuto    BYTEA   NOT NULL,
    creato       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (guild_id, case_number)
);
