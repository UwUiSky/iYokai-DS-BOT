-- #125 r6eco (ECO-018, 027, 045, 054, 056, 083-085, 087, 142, 144-147): gettoni globali, vacanza, diretta, casa, fattoria,
-- personaggi, borsa, autovendita, eventi a tempo e codici in chat.
ALTER TABLE progress_serie ADD COLUMN IF NOT EXISTS vacanza_da TIMESTAMPTZ;
ALTER TABLE progress_serie ADD COLUMN IF NOT EXISTS vacanza_fino TIMESTAMPTZ;

-- ECO-018: seconda moneta, una per persona e valida in tutti i server; non si converte in monete.
CREATE TABLE IF NOT EXISTS economia_gettoni (
    user_id BIGINT PRIMARY KEY,
    saldo   BIGINT NOT NULL DEFAULT 0 CHECK (saldo >= 0)
);
-- ECO-087: i mobili della casa (globale come i gettoni).
CREATE TABLE IF NOT EXISTS economia_casa (
    user_id BIGINT NOT NULL,
    mobile  TEXT   NOT NULL,
    PRIMARY KEY (user_id, mobile)
);
-- ECO-045: serie della diretta.
CREATE TABLE IF NOT EXISTS economia_diretta (
    guild_id BIGINT NOT NULL,
    user_id  BIGINT NOT NULL,
    serie    INTEGER NOT NULL DEFAULT 0,
    ultimo   DATE,
    PRIMARY KEY (guild_id, user_id)
);
-- ECO-146: orto con tre posti.
CREATE TABLE IF NOT EXISTS economia_fattoria (
    guild_id    BIGINT NOT NULL,
    user_id     BIGINT NOT NULL,
    posto       INTEGER NOT NULL CHECK (posto BETWEEN 1 AND 3),
    coltura     TEXT   NOT NULL,
    piantato_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (guild_id, user_id, posto)
);
-- ECO-142: una missione al giorno per personaggio.
CREATE TABLE IF NOT EXISTS economia_personaggi (
    guild_id BIGINT NOT NULL,
    user_id  BIGINT NOT NULL,
    npc      TEXT   NOT NULL,
    giorno   DATE   NOT NULL,
    PRIMARY KEY (guild_id, user_id, npc)
);
-- ECO-084: prezzi della borsa finta (uguali per tutti i server), ECO-085 ordini a soglia, titoli posseduti.
CREATE TABLE IF NOT EXISTS economia_borsa_prezzi (
    simbolo       TEXT PRIMARY KEY,
    prezzo        INTEGER NOT NULL CHECK (prezzo > 0),
    aggiornato_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS economia_borsa (
    guild_id BIGINT NOT NULL,
    user_id  BIGINT NOT NULL,
    simbolo  TEXT   NOT NULL,
    quote    INTEGER NOT NULL CHECK (quote >= 0),
    PRIMARY KEY (guild_id, user_id, simbolo)
);
CREATE TABLE IF NOT EXISTS economia_borsa_ordini (
    id       BIGSERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    user_id  BIGINT NOT NULL,
    simbolo  TEXT   NOT NULL,
    lato     TEXT   NOT NULL CHECK (lato IN ('compra', 'vendi')),
    quote    INTEGER NOT NULL CHECK (quote BETWEEN 1 AND 100),
    soglia   INTEGER NOT NULL CHECK (soglia > 0)
);
CREATE INDEX IF NOT EXISTS economia_borsa_ordini_utente ON economia_borsa_ordini (guild_id, user_id);
-- ECO-083: vendita automatica di un oggetto quando il cambio del giorno arriva alla soglia.
CREATE TABLE IF NOT EXISTS economia_autovendita (
    guild_id BIGINT  NOT NULL,
    user_id  BIGINT  NOT NULL,
    item_id  INTEGER NOT NULL,
    soglia   INTEGER NOT NULL CHECK (soglia BETWEEN 40 AND 60),
    PRIMARY KEY (guild_id, user_id, item_id)
);
-- ECO-054, 056, 145: eventi in chat da prendere per primi (codice da scrivere, bonus a tempo, evento raro).
CREATE TABLE IF NOT EXISTS economia_chat_eventi (
    id         BIGSERIAL PRIMARY KEY,
    guild_id   BIGINT NOT NULL,
    tipo       TEXT   NOT NULL CHECK (tipo IN ('codice', 'bonus', 'raro')),
    codice     TEXT,
    monete     INTEGER NOT NULL DEFAULT 0 CHECK (monete BETWEEN 0 AND 100000),
    percento   INTEGER NOT NULL DEFAULT 0 CHECK (percento BETWEEN 0 AND 100),
    minuti     INTEGER NOT NULL DEFAULT 0 CHECK (minuti BETWEEN 0 AND 1440),
    scade_at   TIMESTAMPTZ NOT NULL,
    preso_da   BIGINT,
    creato_da  BIGINT NOT NULL
);
-- ECO-056, 144: bonus a tempo su lavoro e premio, per una persona (user_id) o per tutto il server (user_id = 0).
CREATE TABLE IF NOT EXISTS economia_bonus_tempo (
    guild_id BIGINT NOT NULL,
    user_id  BIGINT NOT NULL,
    percento INTEGER NOT NULL CHECK (percento BETWEEN 1 AND 100),
    fino     TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (guild_id, user_id)
);
-- ECO-144, 145: eventi casuali del server in un canale scelto.
CREATE TABLE IF NOT EXISTS economia_eventi_conf (
    guild_id  BIGINT PRIMARY KEY,
    canale_id BIGINT NOT NULL,
    attivo    BOOLEAN NOT NULL DEFAULT TRUE,
    ultimo_at TIMESTAMPTZ
);
