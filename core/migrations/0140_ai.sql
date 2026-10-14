-- NF-24 (#95, #50, #132): motore AI. Tutto parte spento; si accende per server con il consenso dell'admin.
-- Solo numeri nell'uso, mai il testo. Le risposte nate dai messaggi di un server restano in quel server.

CREATE TABLE IF NOT EXISTS ai_config (
    guild_id                  BIGINT PRIMARY KEY,
    attivo                    BOOLEAN NOT NULL DEFAULT FALSE,
    consenso_da               BIGINT,
    consenso_il               TIMESTAMPTZ,
    canali_spenti             BIGINT[] NOT NULL DEFAULT '{}',
    tetto_mensile_cent        INTEGER NOT NULL DEFAULT 0 CHECK (tetto_mensile_cent >= 0),
    quota_utente_giorno       INTEGER NOT NULL DEFAULT 20 CHECK (quota_utente_giorno >= 0),
    quota_utente_30g          INTEGER NOT NULL DEFAULT 300 CHECK (quota_utente_30g >= 0),
    quota_funzione_giorno     INTEGER NOT NULL DEFAULT 500 CHECK (quota_funzione_giorno >= 0),
    quota_immagini_settimana  INTEGER NOT NULL DEFAULT 5 CHECK (quota_immagini_settimana >= 0),
    prezzo_pacchetto_immagini INTEGER NOT NULL DEFAULT 0 CHECK (prezzo_pacchetto_immagini >= 0),
    privacy                   TEXT NOT NULL DEFAULT 'completa' CHECK (privacy IN ('completa', 'senza_messaggi')),
    lunghezza                 TEXT NOT NULL DEFAULT 'media' CHECK (lunghezza IN ('corta', 'media', 'lunga')),
    conservazione_minuti      INTEGER NOT NULL DEFAULT 30 CHECK (conservazione_minuti BETWEEN 0 AND 1440),
    lore_tema                 TEXT,
    lore_testo                TEXT,
    parole_vietate            TEXT[] NOT NULL DEFAULT '{}',
    menzione                  BOOLEAN NOT NULL DEFAULT FALSE,
    bandiere                  BOOLEAN NOT NULL DEFAULT FALSE,
    moderazione_canali        BIGINT[] NOT NULL DEFAULT '{}',
    aggiornato_il             TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ai_uso (
    id               BIGSERIAL PRIMARY KEY,
    guild_id         BIGINT NOT NULL,
    user_id          BIGINT NOT NULL,
    funzione         TEXT NOT NULL,
    fornitore        TEXT NOT NULL,
    immagine         BOOLEAN NOT NULL DEFAULT FALSE,
    token_in         INTEGER NOT NULL DEFAULT 0,
    token_out        INTEGER NOT NULL DEFAULT 0,
    costo_millesimi  INTEGER NOT NULL DEFAULT 0,
    creato_il        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ai_uso_guild_data ON ai_uso (guild_id, creato_il);
CREATE INDEX IF NOT EXISTS ai_uso_utente_data ON ai_uso (guild_id, user_id, creato_il);

-- guild_id = 0: libreria comune (testi scritti dall'AI da zero, senza messaggi di utenti).
CREATE TABLE IF NOT EXISTS ai_cache (
    guild_id   BIGINT NOT NULL,
    chiave     TEXT NOT NULL,
    tipo       TEXT NOT NULL,
    risposta   TEXT NOT NULL,
    usi        INTEGER NOT NULL DEFAULT 1,
    creato_il  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (guild_id, chiave)
);

CREATE TABLE IF NOT EXISTS ai_conoscenza (
    id         SERIAL PRIMARY KEY,
    guild_id   BIGINT NOT NULL,
    titolo     TEXT NOT NULL,
    testo      TEXT NOT NULL,
    creato_da  BIGINT NOT NULL,
    creato_il  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ai_conoscenza_guild ON ai_conoscenza (guild_id);

CREATE TABLE IF NOT EXISTS ai_personaggi (
    id         SERIAL PRIMARY KEY,
    guild_id   BIGINT NOT NULL,
    autore_id  BIGINT NOT NULL,
    nome       TEXT NOT NULL,
    biografia  TEXT NOT NULL DEFAULT '',
    tratti     TEXT NOT NULL DEFAULT '',
    gusti      TEXT NOT NULL DEFAULT '',
    fatti      TEXT NOT NULL DEFAULT '',
    installato BOOLEAN NOT NULL DEFAULT FALSE,
    creato_il  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (guild_id, nome)
);

CREATE TABLE IF NOT EXISTS ai_traduzione_canali (
    channel_id BIGINT PRIMARY KEY,
    guild_id   BIGINT NOT NULL,
    lingua     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ai_traduzione_canali_guild ON ai_traduzione_canali (guild_id);

-- Immagini in più comprate con le monete del server (AI-008).
CREATE TABLE IF NOT EXISTS ai_crediti (
    guild_id        BIGINT NOT NULL,
    user_id         BIGINT NOT NULL,
    immagini_extra  INTEGER NOT NULL DEFAULT 0 CHECK (immagini_extra >= 0),
    PRIMARY KEY (guild_id, user_id)
);
