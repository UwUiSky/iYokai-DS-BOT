-- Registro dei file in quarantena (D61, D62): serve a cancellarli quando scadono e con /privacy.
-- Nessun dato dell'autore: solo impronta, nome casuale del file e server.
CREATE TABLE IF NOT EXISTS quarantena_file (
    id        BIGSERIAL PRIMARY KEY,
    sha256    TEXT NOT NULL,
    nome      TEXT NOT NULL UNIQUE CHECK (nome ~ '^[0-9a-f]{32}$'),
    guild_id  BIGINT NOT NULL,
    creato_il TIMESTAMPTZ NOT NULL DEFAULT now(),
    scade_il  TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_quarantena_file_scade ON quarantena_file (scade_il);
CREATE INDEX IF NOT EXISTS idx_quarantena_file_guild ON quarantena_file (guild_id);
