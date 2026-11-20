-- #125 B13 (ECO-122..124, 130, 131, 132..134, 138): animali da accudire e pesca.
CREATE TABLE IF NOT EXISTS economia_animali (
    id        BIGSERIAL PRIMARY KEY,
    guild_id  BIGINT NOT NULL,
    user_id   BIGINT NOT NULL,
    specie    TEXT   NOT NULL,
    nome      TEXT   NOT NULL,
    nato_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    fame_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    igiene_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    gioco_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    attivita_at TIMESTAMPTZ,
    xp        INTEGER NOT NULL DEFAULT 0 CHECK (xp >= 0)
);
CREATE INDEX IF NOT EXISTS economia_animali_utente ON economia_animali (guild_id, user_id);

-- Posti in più oltre al primo (ECO-124).
CREATE TABLE IF NOT EXISTS economia_animali_posti (
    guild_id BIGINT NOT NULL,
    user_id  BIGINT NOT NULL,
    extra    INTEGER NOT NULL DEFAULT 0 CHECK (extra BETWEEN 0 AND 2),
    PRIMARY KEY (guild_id, user_id)
);

-- Deposito dei pesci (ECO-133) e specie viste (ECO-134).
CREATE TABLE IF NOT EXISTS economia_pesci (
    guild_id BIGINT NOT NULL,
    user_id  BIGINT NOT NULL,
    specie   TEXT   NOT NULL,
    quantita INTEGER NOT NULL CHECK (quantita >= 0),
    PRIMARY KEY (guild_id, user_id, specie)
);
CREATE TABLE IF NOT EXISTS economia_pesci_visti (
    guild_id BIGINT NOT NULL,
    user_id  BIGINT NOT NULL,
    specie   TEXT   NOT NULL,
    PRIMARY KEY (guild_id, user_id, specie)
);

-- Punti di pesca di oggi (ECO-138).
CREATE TABLE IF NOT EXISTS economia_pesca_giorno (
    guild_id BIGINT NOT NULL,
    giorno   DATE   NOT NULL,
    user_id  BIGINT NOT NULL,
    punti    INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (guild_id, giorno, user_id)
);
