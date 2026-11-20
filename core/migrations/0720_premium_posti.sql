-- CFG-034 (#122): posti premium legati a una persona. L'owner concede N posti (a tempo o permanenti);
-- la persona li assegna ai server che amministra e li sposta quando vuole (al massimo un cambio all'ora).
-- Registro contabile: si conserva anche se la persona chiede la cancellazione (core/data_registry.py).
CREATE TABLE IF NOT EXISTS premium_posti_utente (
    user_id       BIGINT PRIMARY KEY,
    posti         INTEGER NOT NULL CHECK (posti BETWEEN 1 AND 10),
    scade_il      TIMESTAMPTZ,
    concesso_da   BIGINT NOT NULL,
    creato_il     TIMESTAMPTZ NOT NULL DEFAULT now(),
    ultimo_cambio TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS premium_posti_server (
    guild_id     BIGINT PRIMARY KEY,
    user_id      BIGINT NOT NULL REFERENCES premium_posti_utente (user_id) ON DELETE CASCADE,
    assegnato_il TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_premium_posti_server_utente ON premium_posti_server (user_id);
