-- NF-21 (#92): verifica su pagina web e account doppi.
-- `impronta` è un HMAC con sale segreto e id del server: mai l'IP in chiaro,
-- mai confrontabile tra due server. Le righe scadono (core/data_registry.py).
CREATE TABLE IF NOT EXISTS verify_impronte (
    guild_id   BIGINT NOT NULL,
    user_id    BIGINT NOT NULL,
    tipo       TEXT NOT NULL CHECK (tipo IN ('ip', 'browser')),
    impronta   TEXT NOT NULL,
    creato_il  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (guild_id, user_id, tipo)
);
CREATE INDEX IF NOT EXISTS idx_verify_impronte_cerca ON verify_impronte (guild_id, tipo, impronta);
CREATE INDEX IF NOT EXISTS idx_verify_impronte_creato ON verify_impronte (creato_il);

-- I doppi trovati, per `/security alt elenco`.
CREATE TABLE IF NOT EXISTS verify_doppi (
    guild_id       BIGINT NOT NULL,
    user_id        BIGINT NOT NULL,
    altro_user_id  BIGINT NOT NULL,
    livello        TEXT NOT NULL CHECK (livello IN ('alto', 'medio')),
    trovato_il     TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (guild_id, user_id, altro_user_id)
);
CREATE INDEX IF NOT EXISTS idx_verify_doppi_recenti ON verify_doppi (guild_id, trovato_il DESC);
