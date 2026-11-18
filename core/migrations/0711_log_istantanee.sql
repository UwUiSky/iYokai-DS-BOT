-- LOG-028 (#119): istantanee di un canale consultabili sul pannello web. Il link ha un segreto lungo: nel
-- database resta solo l'impronta SHA-256. Scadono da sole (al massimo 7 giorni) e sono al massimo 5 per server.
-- Le righe hanno il testo dei messaggi (già troncato, senza file: solo i nomi): si cancellano con il server,
-- con l'autore (richiesta privacy) e con l'istantanea.
CREATE TABLE IF NOT EXISTS log_istantanee (
    id          BIGSERIAL PRIMARY KEY,
    guild_id    BIGINT      NOT NULL,
    channel_id  BIGINT      NOT NULL,
    nome_canale TEXT        NOT NULL CHECK (char_length(nome_canale) <= 100),
    creata_da   BIGINT      NOT NULL,
    creata_il   TIMESTAMPTZ NOT NULL DEFAULT now(),
    scade_il    TIMESTAMPTZ NOT NULL,
    accesso     TEXT        NOT NULL CHECK (accesso IN ('gestori', 'ruolo', 'membri')),
    role_id     BIGINT,
    impronta    TEXT        NOT NULL UNIQUE CHECK (char_length(impronta) = 64),
    CHECK (accesso <> 'ruolo' OR role_id IS NOT NULL)
);
CREATE INDEX IF NOT EXISTS log_istantanee_server ON log_istantanee (guild_id, scade_il);

CREATE TABLE IF NOT EXISTS log_istantanee_righe (
    istantanea_id BIGINT  NOT NULL REFERENCES log_istantanee (id) ON DELETE CASCADE,
    posizione     INTEGER NOT NULL,
    guild_id      BIGINT  NOT NULL,
    message_id    BIGINT,
    author_id     BIGINT,
    autore_nome   TEXT    NOT NULL CHECK (char_length(autore_nome) <= 100),
    quando        TEXT    NOT NULL CHECK (char_length(quando) <= 32),
    testo         TEXT    NOT NULL CHECK (char_length(testo) <= 2100),
    cancellato    BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (istantanea_id, posizione)
);
CREATE INDEX IF NOT EXISTS log_istantanee_righe_autore ON log_istantanee_righe (author_id);
