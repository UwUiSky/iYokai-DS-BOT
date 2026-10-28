-- iYokai Desktop (D.1-D.10, #108): accesso con token personale, scelte di avviso, eventi per l'utente, azioni dello staff.
-- Il token si conserva solo come impronta (SHA-256). Gli eventi contengono un testo breve di altre persone:
-- si cancellano dopo 90 giorni e su richiesta (core/data_registry.py).

CREATE TABLE IF NOT EXISTS desktop_tokens (
    user_id      BIGINT PRIMARY KEY,
    token_hash   TEXT NOT NULL UNIQUE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_used_at TIMESTAMPTZ
);

-- Menzioni e parole chiave: spenti finché la persona non li accende.
CREATE TABLE IF NOT EXISTS desktop_prefs (
    user_id  BIGINT PRIMARY KEY,
    menzioni BOOLEAN NOT NULL DEFAULT FALSE,
    parole   TEXT[] NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS desktop_eventi (
    id          BIGSERIAL PRIMARY KEY,
    user_id     BIGINT NOT NULL,
    tipo        TEXT NOT NULL,
    guild_id    BIGINT,
    channel_id  BIGINT,
    message_id  BIGINT,
    autore_id   BIGINT,
    autore_nome TEXT,
    canale_nome TEXT,
    testo       TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS desktop_eventi_utente ON desktop_eventi (user_id, id);

-- Azioni eseguite dal bot su richiesta del programma (pannello rapido dello staff).
CREATE TABLE IF NOT EXISTS desktop_azioni (
    id         BIGSERIAL PRIMARY KEY,
    user_id    BIGINT NOT NULL,
    guild_id   BIGINT NOT NULL,
    azione     TEXT NOT NULL,
    dettaglio  TEXT NOT NULL DEFAULT '',
    esito      TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS desktop_azioni_server ON desktop_azioni (guild_id, id DESC);
