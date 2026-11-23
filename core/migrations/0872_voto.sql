-- r1rep (LIV-019, ECO-048, ECO-049, CFG-039): voto al bot su un sito di elenchi. Spento finché l'owner non mette la chiave.
CREATE TABLE IF NOT EXISTS voto_impostazioni (
    guild_id        BIGINT PRIMARY KEY,
    attivo          BOOLEAN NOT NULL DEFAULT FALSE,
    xp_bonus_pct    INTEGER NOT NULL DEFAULT 10 CHECK (xp_bonus_pct BETWEEN 0 AND 100),
    xp_bonus_ore    INTEGER NOT NULL DEFAULT 12 CHECK (xp_bonus_ore BETWEEN 1 AND 48),
    monete          INTEGER NOT NULL DEFAULT 0 CHECK (monete BETWEEN 0 AND 100000),
    xp              INTEGER NOT NULL DEFAULT 0 CHECK (xp BETWEEN 0 AND 100000),
    premium_giorni  INTEGER NOT NULL DEFAULT 0 CHECK (premium_giorni BETWEEN 0 AND 30)
);

CREATE TABLE IF NOT EXISTS voti (
    id                BIGSERIAL PRIMARY KEY,
    sito              TEXT NOT NULL CHECK (char_length(sito) <= 20),
    user_id           BIGINT NOT NULL,
    ricevuto_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    riscattato_guild  BIGINT,
    riscattato_at     TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS voti_utente ON voti (user_id, ricevuto_at DESC);

-- Riscatto automatico (ECO-049): il server dove arriva il premio appena il voto è registrato.
CREATE TABLE IF NOT EXISTS voto_utenti (
    user_id     BIGINT PRIMARY KEY,
    auto_guild  BIGINT
);

CREATE TABLE IF NOT EXISTS voto_bonus (
    guild_id BIGINT NOT NULL,
    user_id  BIGINT NOT NULL,
    fino_a   TIMESTAMPTZ NOT NULL,
    pct      INTEGER NOT NULL CHECK (pct BETWEEN 1 AND 100),
    PRIMARY KEY (guild_id, user_id)
);
