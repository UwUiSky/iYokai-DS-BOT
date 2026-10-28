-- NF-24 (r12): World Boss, dungeon di gruppo, misteri, spiriti, frammenti di lore.
-- Le storie e i mostri della libreria (ai_storie, ai_storie_nodi, ai_mostri) sono testi scritti
-- dall'AI da zero: valgono in ogni server con lo stesso tema e non contengono dati di utenti.

CREATE TABLE IF NOT EXISTS ai_boss_config (
    guild_id         BIGINT PRIMARY KEY,
    attivo           BOOLEAN NOT NULL DEFAULT FALSE,
    canale_id        BIGINT,
    giorni           SMALLINT[] NOT NULL DEFAULT '{}',
    ora              SMALLINT NOT NULL DEFAULT 21 CHECK (ora BETWEEN 0 AND 23),
    fuso             TEXT NOT NULL DEFAULT 'Europe/Rome',
    rete             BOOLEAN NOT NULL DEFAULT FALSE,
    ruolo_premio_id  BIGINT,
    ruolo_premio_ore SMALLINT NOT NULL DEFAULT 24 CHECK (ruolo_premio_ore BETWEEN 1 AND 168),
    ultimo_giorno    DATE
);

CREATE TABLE IF NOT EXISTS ai_boss_rete (
    id          SERIAL PRIMARY KEY,
    nome        TEXT NOT NULL,
    aspetto     TEXT NOT NULL DEFAULT '',
    frasi       TEXT[] NOT NULL DEFAULT '{}',
    vita_extra  INTEGER NOT NULL DEFAULT 0 CHECK (vita_extra >= 0),
    attivo      BOOLEAN NOT NULL DEFAULT TRUE,
    creato_da   BIGINT NOT NULL,
    creato_il   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ai_boss_eventi (
    id          BIGSERIAL PRIMARY KEY,
    guild_id    BIGINT NOT NULL,
    channel_id  BIGINT NOT NULL,
    message_id  BIGINT,
    nome        TEXT NOT NULL,
    aspetto     TEXT NOT NULL DEFAULT '',
    frasi       TEXT[] NOT NULL DEFAULT '{}',
    vita_max    INTEGER NOT NULL CHECK (vita_max > 0),
    vita        INTEGER NOT NULL CHECK (vita >= 0),
    azioni      INTEGER NOT NULL DEFAULT 0,
    stato       TEXT NOT NULL DEFAULT 'attivo' CHECK (stato IN ('attivo', 'sconfitto', 'fuggito')),
    rete_id     INTEGER,
    creato_il   TIMESTAMPTZ NOT NULL DEFAULT now(),
    scade_il    TIMESTAMPTZ NOT NULL,
    chiuso_il   TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS ai_boss_eventi_guild ON ai_boss_eventi (guild_id, stato);
CREATE UNIQUE INDEX IF NOT EXISTS ai_boss_uno_per_canale ON ai_boss_eventi (channel_id) WHERE stato = 'attivo';

CREATE TABLE IF NOT EXISTS ai_boss_colpi (
    evento_id    BIGINT NOT NULL REFERENCES ai_boss_eventi (id) ON DELETE CASCADE,
    user_id      BIGINT NOT NULL,
    danno        INTEGER NOT NULL DEFAULT 0,
    azioni       INTEGER NOT NULL DEFAULT 0,
    guardia      BOOLEAN NOT NULL DEFAULT FALSE,
    ferito_fino  TIMESTAMPTZ,
    ultima_azione TIMESTAMPTZ,
    PRIMARY KEY (evento_id, user_id)
);

-- Contatore in comune del boss di rete: solo totali per server, mai persone.
CREATE TABLE IF NOT EXISTS ai_boss_rete_totali (
    rete_id        INTEGER NOT NULL REFERENCES ai_boss_rete (id) ON DELETE CASCADE,
    guild_id       BIGINT NOT NULL,
    danno_totale   BIGINT NOT NULL DEFAULT 0,
    partecipanti   INTEGER NOT NULL DEFAULT 0,
    sconfitto      BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (rete_id, guild_id)
);

CREATE TABLE IF NOT EXISTS ai_mostri (
    id        SERIAL PRIMARY KEY,
    tema      TEXT NOT NULL,
    nome      TEXT NOT NULL,
    aspetto   TEXT NOT NULL DEFAULT '',
    frasi     TEXT[] NOT NULL DEFAULT '{}',
    creato_il TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tema, nome)
);

CREATE TABLE IF NOT EXISTS ai_storie (
    id        SERIAL PRIMARY KEY,
    tema      TEXT NOT NULL,
    titolo    TEXT NOT NULL,
    inizio    TEXT NOT NULL DEFAULT 'inizio',
    creato_il TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tema, titolo)
);

CREATE TABLE IF NOT EXISTS ai_storie_nodi (
    storia_id  INTEGER NOT NULL REFERENCES ai_storie (id) ON DELETE CASCADE,
    nodo       TEXT NOT NULL,
    testo      TEXT NOT NULL,
    finale     BOOLEAN NOT NULL DEFAULT FALSE,
    esito      TEXT NOT NULL DEFAULT 'neutro' CHECK (esito IN ('vittoria', 'sconfitta', 'neutro')),
    scelte     JSONB NOT NULL DEFAULT '[]',
    PRIMARY KEY (storia_id, nodo)
);

CREATE TABLE IF NOT EXISTS ai_dungeon_partite (
    id          BIGSERIAL PRIMARY KEY,
    guild_id    BIGINT NOT NULL,
    channel_id  BIGINT NOT NULL,
    message_id  BIGINT,
    storia_id   INTEGER NOT NULL,
    nodo        TEXT NOT NULL,
    stato       TEXT NOT NULL DEFAULT 'lobby' CHECK (stato IN ('lobby', 'in_corso', 'finita')),
    scade_il    TIMESTAMPTZ NOT NULL,
    cronologia  TEXT[] NOT NULL DEFAULT '{}',
    esito       TEXT,
    creato_il   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ai_dungeon_partite_guild ON ai_dungeon_partite (guild_id, stato);
CREATE UNIQUE INDEX IF NOT EXISTS ai_dungeon_una_per_canale ON ai_dungeon_partite (channel_id) WHERE stato <> 'finita';

CREATE TABLE IF NOT EXISTS ai_dungeon_giocatori (
    partita_id BIGINT NOT NULL REFERENCES ai_dungeon_partite (id) ON DELETE CASCADE,
    user_id    BIGINT NOT NULL,
    classe     TEXT NOT NULL,
    voto       SMALLINT,
    PRIMARY KEY (partita_id, user_id)
);

CREATE TABLE IF NOT EXISTS ai_misteri (
    id            SERIAL PRIMARY KEY,
    guild_id      BIGINT NOT NULL,
    titolo        TEXT NOT NULL,
    indizio       TEXT NOT NULL,
    codice_hash   TEXT NOT NULL,
    premio        TEXT NOT NULL CHECK (premio IN ('xp', 'canale')),
    premio_valore BIGINT NOT NULL DEFAULT 0,
    durata_ore    SMALLINT NOT NULL DEFAULT 24 CHECK (durata_ore BETWEEN 1 AND 168),
    stato         TEXT NOT NULL DEFAULT 'aperto' CHECK (stato IN ('aperto', 'risolto')),
    risolto_da    BIGINT,
    risolto_il    TIMESTAMPTZ,
    creato_da     BIGINT NOT NULL,
    creato_il     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ai_misteri_guild ON ai_misteri (guild_id, stato);

CREATE TABLE IF NOT EXISTS ai_spiriti (
    guild_id  BIGINT NOT NULL,
    user_id   BIGINT NOT NULL,
    scelto    TEXT,
    PRIMARY KEY (guild_id, user_id)
);

CREATE TABLE IF NOT EXISTS ai_frammenti (
    guild_id     BIGINT NOT NULL,
    user_id      BIGINT NOT NULL,
    codice       TEXT NOT NULL,
    sbloccato_il TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (guild_id, user_id, codice)
);
