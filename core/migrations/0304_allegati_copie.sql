-- Copie sicure degli allegati dei log dei messaggi (D61, #152): i byte stanno in una cartella fuori dal sito,
-- qui solo il registro. `nome` e `anteprima` sono nomi casuali di 32 cifre esadecimali.
CREATE TABLE IF NOT EXISTS allegati_copie (
    id          BIGSERIAL   PRIMARY KEY,
    guild_id    BIGINT      NOT NULL,
    channel_id  BIGINT      NOT NULL,
    message_id  BIGINT      NOT NULL,
    user_id     BIGINT      NOT NULL,
    origine     TEXT        NOT NULL,
    nome_file   TEXT        NOT NULL,
    tipo        TEXT        NOT NULL,
    sha256      TEXT        NOT NULL,
    dimensione  INTEGER     NOT NULL,
    nome        TEXT        UNIQUE CHECK (nome ~ '^[0-9a-f]{32}$'),
    anteprima   TEXT        UNIQUE CHECK (anteprima ~ '^[0-9a-f]{32}$'),
    stato       TEXT        NOT NULL DEFAULT 'salvata',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    scade_il    TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_allegati_copie_messaggio ON allegati_copie (guild_id, message_id);
CREATE INDEX IF NOT EXISTS idx_allegati_copie_scade ON allegati_copie (scade_il);
CREATE INDEX IF NOT EXISTS idx_allegati_copie_utente ON allegati_copie (user_id);
