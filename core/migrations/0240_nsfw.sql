-- NF-23 (#94): istanza NSFW. Scelte del server, pubblicazione automatica, registro con l'impronta (SHA-256)
-- di ogni immagine pubblicata e contenuti bloccati (per impronta o per id della fonte) in tutti i server.
CREATE TABLE IF NOT EXISTS nsfw_config (
    guild_id      BIGINT PRIMARY KEY,
    attivo        BOOLEAN NOT NULL DEFAULT FALSE,
    tag_permessi  TEXT[] NOT NULL DEFAULT '{}',
    attivato_da   BIGINT,
    aggiornato_il TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS nsfw_autopost (
    guild_id          BIGINT NOT NULL,
    channel_id        BIGINT NOT NULL,
    tag               TEXT NOT NULL,
    intervallo_minuti INTEGER NOT NULL CHECK (intervallo_minuti >= 30),
    prossimo_il       TIMESTAMPTZ NOT NULL DEFAULT now(),
    errori            INTEGER NOT NULL DEFAULT 0,
    creato_da         BIGINT NOT NULL,
    PRIMARY KEY (guild_id, channel_id)
);
CREATE INDEX IF NOT EXISTS idx_nsfw_autopost_prossimo ON nsfw_autopost (prossimo_il);

CREATE TABLE IF NOT EXISTS nsfw_registro (
    id         BIGSERIAL PRIMARY KEY,
    guild_id   BIGINT NOT NULL,
    channel_id BIGINT NOT NULL,
    message_id BIGINT,
    fonte      TEXT NOT NULL,
    id_fonte   TEXT NOT NULL,
    impronta   TEXT NOT NULL,
    inviato_il TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_nsfw_registro_impronta ON nsfw_registro (guild_id, impronta);
CREATE INDEX IF NOT EXISTS idx_nsfw_registro_messaggio ON nsfw_registro (message_id);

CREATE TABLE IF NOT EXISTS nsfw_bloccati (
    impronta     TEXT PRIMARY KEY,
    fonte        TEXT NOT NULL,
    id_fonte     TEXT NOT NULL,
    motivo       TEXT NOT NULL,
    guild_id     BIGINT,
    segnalato_da BIGINT,
    creato_il    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_nsfw_bloccati_fonte ON nsfw_bloccati (fonte, id_fonte);
