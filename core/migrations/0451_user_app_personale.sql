-- iYokai App, voci B.2, B.5, B.8, B.9, B.10 (NF-36, #107): dati personali dell'utente.
-- Tutte le righe sono dell'utente: si cancellano con la sua richiesta e si esportano (core/data_registry.py).

-- B.2 Segnalibri: testo e link di un messaggio scelto dall'utente (il nome dell'autore è solo testo).
CREATE TABLE IF NOT EXISTS user_app_bookmarks (
    id          BIGSERIAL PRIMARY KEY,
    user_id     BIGINT NOT NULL,
    guild_id    BIGINT,
    channel_id  BIGINT NOT NULL,
    message_id  BIGINT NOT NULL,
    autore      TEXT NOT NULL,
    testo       TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, message_id)
);

-- B.5 Risposte salvate: un testo, o un embed (titolo, colore, immagine), richiamabile con il nome.
CREATE TABLE IF NOT EXISTS user_app_replies (
    id           BIGSERIAL PRIMARY KEY,
    user_id      BIGINT NOT NULL,
    nome         TEXT NOT NULL,
    testo        TEXT NOT NULL,
    titolo       TEXT,
    colore       INTEGER,
    immagine_url TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, nome)
);

-- B.10 Impostazioni personali. La lingua sta in `user_language`.
CREATE TABLE IF NOT EXISTS user_app_settings (
    user_id          BIGINT PRIMARY KEY,
    risposte_private BOOLEAN NOT NULL DEFAULT TRUE,
    dm_ok            BOOLEAN NOT NULL DEFAULT TRUE,
    storico          BOOLEAN NOT NULL DEFAULT FALSE,
    profilo_pubblico BOOLEAN NOT NULL DEFAULT FALSE,
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- B.10, D.7 Storico dei propri comandi: solo se l'utente lo accende; tetto 100 righe, 90 giorni.
CREATE TABLE IF NOT EXISTS user_app_history (
    id       BIGSERIAL PRIMARY KEY,
    user_id  BIGINT NOT NULL,
    comando  TEXT NOT NULL,
    guild_id BIGINT,
    used_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_user_app_history_utente ON user_app_history (user_id, id DESC);
CREATE INDEX IF NOT EXISTS idx_user_app_history_data ON user_app_history (used_at);

-- B.8 Playlist personali: nome e brani (titoli o link), come testo.
CREATE TABLE IF NOT EXISTS user_app_playlists (
    id         BIGSERIAL PRIMARY KEY,
    user_id    BIGINT NOT NULL,
    nome       TEXT NOT NULL,
    brani      TEXT[] NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, nome)
);

-- B.9 Richieste di assistenza a iYokai da qualsiasi server: un thread nel canale dello staff.
CREATE TABLE IF NOT EXISTS support_requests (
    id         BIGSERIAL PRIMARY KEY,
    user_id    BIGINT NOT NULL,
    oggetto    TEXT NOT NULL,
    testo      TEXT NOT NULL,
    stato      TEXT NOT NULL DEFAULT 'aperta',
    thread_id  BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    closed_at  TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_support_requests_utente ON support_requests (user_id, id DESC);
CREATE INDEX IF NOT EXISTS idx_support_requests_thread ON support_requests (thread_id);
