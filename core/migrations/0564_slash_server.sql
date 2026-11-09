-- D69 B28: comandi e menu del server che rispondono con un tag, e lo stato della sync con Discord per server.
CREATE TABLE IF NOT EXISTS comandi_server (
    id          BIGSERIAL PRIMARY KEY,
    guild_id    BIGINT NOT NULL,
    nome        TEXT   NOT NULL CHECK (char_length(nome) BETWEEN 1 AND 32),
    sotto       TEXT   NOT NULL DEFAULT '' CHECK (char_length(sotto) <= 32),
    tag         TEXT   NOT NULL,
    descrizione TEXT   NOT NULL CHECK (char_length(descrizione) BETWEEN 1 AND 100),
    creato_da   BIGINT,
    creato_il   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (guild_id, nome, sotto)
);

CREATE TABLE IF NOT EXISTS menu_server (
    id        BIGSERIAL PRIMARY KEY,
    guild_id  BIGINT NOT NULL,
    nome      TEXT   NOT NULL CHECK (char_length(nome) BETWEEN 1 AND 32),
    tipo      TEXT   NOT NULL CHECK (tipo IN ('utente', 'messaggio')),
    tag       TEXT   NOT NULL,
    creato_da BIGINT,
    creato_il TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (guild_id, nome, tipo)
);

CREATE TABLE IF NOT EXISTS slash_server_stato (
    guild_id    BIGINT PRIMARY KEY,
    ultimo_sync TIMESTAMPTZ,
    impronta    TEXT NOT NULL DEFAULT '',
    nomi        JSONB NOT NULL DEFAULT '[]'::jsonb,
    giorno      DATE,
    creazioni   INT NOT NULL DEFAULT 0,
    in_coda     BOOLEAN NOT NULL DEFAULT FALSE
);
