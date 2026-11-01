-- D53: paese dell'account nella verifica web. Solo il codice ISO a 2 lettere e la lingua del
-- client Discord: mai l'IP, mai la città. Le righe scadono (core/data_registry.py).
CREATE TABLE IF NOT EXISTS verify_paese (
    guild_id   BIGINT NOT NULL,
    user_id    BIGINT NOT NULL,
    paese      CHAR(2),
    lingua     TEXT,
    stato      TEXT NOT NULL DEFAULT 'ok' CHECK (stato IN ('ok', 'attesa', 'approvata', 'rifiutata')),
    creato_il  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (guild_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_verify_paese_finestra ON verify_paese (guild_id, creato_il);
