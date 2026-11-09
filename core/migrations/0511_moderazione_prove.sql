-- Prove allegate a un caso o a una nota (MOD-038): al massimo 5 per caso o nota, ognuna fino a 10 MiB.
-- Immagini: solo la copia ricodificata (D62). PDF e TXT: file grezzo, mai aperto, tolto dopo 180 giorni.
CREATE TABLE IF NOT EXISTS moderation_prove (
    id          BIGSERIAL   PRIMARY KEY,
    guild_id    BIGINT      NOT NULL,
    user_id     BIGINT      NOT NULL,
    autore_id   BIGINT      NOT NULL,
    case_number INTEGER,
    nota_id     INTEGER,
    nome_file   TEXT        NOT NULL,
    tipo        TEXT        NOT NULL,
    sha256      TEXT        NOT NULL,
    dimensione  INTEGER     NOT NULL,
    dati        BYTEA       NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT moderation_prove_unica_cosa CHECK ((case_number IS NULL) <> (nota_id IS NULL))
);
CREATE INDEX IF NOT EXISTS idx_moderation_prove_caso ON moderation_prove (guild_id, case_number) WHERE case_number IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_moderation_prove_nota ON moderation_prove (guild_id, nota_id) WHERE nota_id IS NOT NULL;
