-- D63 (AMD-047): decide lo staff. Una riga per ogni decisione chiesta ai moderatori: le sanzioni della regola
-- aspettano qui il bottone «Applica» o «Ignora». L'estratto del messaggio (al massimo 500 caratteri) si cancella
-- dopo 30 giorni (core/data_registry.py).
CREATE TABLE IF NOT EXISTS automod_decisioni (
    id           BIGSERIAL PRIMARY KEY,
    guild_id     BIGINT NOT NULL,
    user_id      BIGINT NOT NULL,
    regola_chiave TEXT NOT NULL,
    regola_nome  TEXT NOT NULL,
    canale_id    BIGINT,
    estratto     TEXT,
    azioni       JSONB NOT NULL DEFAULT '[]'::jsonb,
    stato        TEXT NOT NULL DEFAULT 'attesa' CHECK (stato IN ('attesa', 'applicata', 'ignorata')),
    messaggio_id BIGINT,
    decisa_da    BIGINT,
    decisa_il    TIMESTAMPTZ,
    creata_il    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_automod_decisioni_server ON automod_decisioni (guild_id, stato, creata_il DESC);
CREATE INDEX IF NOT EXISTS idx_automod_decisioni_utente ON automod_decisioni (guild_id, user_id);
