-- r1rep (LIV-076…088): reputazione tra membri. Spenta di base.
CREATE TABLE IF NOT EXISTS reputazione_impostazioni (
    guild_id                BIGINT PRIMARY KEY,
    attiva                  BOOLEAN NOT NULL DEFAULT FALSE,
    nome                    TEXT NOT NULL DEFAULT 'reputazione' CHECK (char_length(nome) BETWEEN 1 AND 20),
    pausa_secondi           INTEGER NOT NULL DEFAULT 86400 CHECK (pausa_secondi BETWEEN 3600 AND 604800),
    massimo_per_comando     INTEGER NOT NULL DEFAULT 1 CHECK (massimo_per_comando BETWEEN 1 AND 10),
    tetto_giornaliero       INTEGER NOT NULL DEFAULT 5 CHECK (tetto_giornaliero BETWEEN 1 AND 100),
    ruolo_togliere          BIGINT,
    ruolo_dare_richiesto    BIGINT,
    ruolo_dare_escluso      BIGINT,
    ruolo_ricevere_richiesto BIGINT,
    ruolo_ricevere_escluso  BIGINT,
    grazie_attivo           BOOLEAN NOT NULL DEFAULT FALSE,
    grazie_canali           BIGINT[] NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS reputazione_punti (
    guild_id BIGINT NOT NULL,
    user_id  BIGINT NOT NULL,
    punti    INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (guild_id, user_id)
);
CREATE INDEX IF NOT EXISTS reputazione_punti_classifica ON reputazione_punti (guild_id, punti DESC);

CREATE TABLE IF NOT EXISTS reputazione_registro (
    id       BIGSERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    da_id    BIGINT NOT NULL,
    a_id     BIGINT NOT NULL,
    delta    INTEGER NOT NULL,
    fonte    TEXT NOT NULL DEFAULT 'utente' CHECK (fonte IN ('utente', 'grazie', 'staff')),
    motivo   TEXT NOT NULL DEFAULT '' CHECK (char_length(motivo) <= 200),
    creato   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS reputazione_registro_a ON reputazione_registro (guild_id, a_id, creato DESC);
CREATE INDEX IF NOT EXISTS reputazione_registro_da ON reputazione_registro (guild_id, da_id, creato DESC);

-- Ultima volta che un utente ha dato o tolto un punto (la pausa si prende con una sola scrittura).
CREATE TABLE IF NOT EXISTS reputazione_pausa (
    guild_id BIGINT NOT NULL,
    user_id  BIGINT NOT NULL,
    ultimo   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (guild_id, user_id)
);

CREATE TABLE IF NOT EXISTS reputazione_premi (
    guild_id BIGINT NOT NULL,
    soglia   INTEGER NOT NULL CHECK (soglia BETWEEN 1 AND 1000000),
    role_id  BIGINT NOT NULL,
    PRIMARY KEY (guild_id, soglia)
);
