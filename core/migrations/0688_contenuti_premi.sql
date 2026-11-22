-- #125 r6eco (ECO-113, 114, 152, 039): premi di quiz e impiccato con tetto giornaliero, righe del profilo, comandi di guadagno del server.
CREATE TABLE IF NOT EXISTS economia_premi_giorno (
    guild_id BIGINT NOT NULL,
    user_id  BIGINT NOT NULL,
    giorno   DATE   NOT NULL,
    tipo     TEXT   NOT NULL,
    totale   BIGINT NOT NULL DEFAULT 0 CHECK (totale >= 0),
    PRIMARY KEY (guild_id, user_id, giorno, tipo)
);

CREATE TABLE IF NOT EXISTS economia_profilo_righe (
    guild_id BIGINT NOT NULL,
    user_id  BIGINT NOT NULL,
    righe    TEXT   NOT NULL CHECK (char_length(righe) <= 120),
    PRIMARY KEY (guild_id, user_id)
);

CREATE TABLE IF NOT EXISTS economia_comandi_guadagno (
    guild_id  BIGINT  NOT NULL,
    nome      TEXT    NOT NULL CHECK (nome ~ '^[a-z0-9-]{1,20}$'),
    minimo    INTEGER NOT NULL CHECK (minimo BETWEEN 0 AND 10000),
    massimo   INTEGER NOT NULL CHECK (massimo BETWEEN 1 AND 10000),
    pausa_s   INTEGER NOT NULL CHECK (pausa_s BETWEEN 60 AND 604800),
    testo     TEXT    NOT NULL CHECK (char_length(testo) BETWEEN 1 AND 200),
    creato_da BIGINT  NOT NULL,
    PRIMARY KEY (guild_id, nome),
    CHECK (minimo <= massimo)
);
