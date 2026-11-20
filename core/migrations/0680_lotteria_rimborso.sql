-- #125 B11 (ECO-117, 118, 121): rimborso di parte delle perdite, lotteria giornaliera e suo registro.
ALTER TABLE leveling_settings
    ADD COLUMN IF NOT EXISTS lotteria_prezzo INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS rimborso_pct    INTEGER NOT NULL DEFAULT 0;

-- Da dove si misurano le perdite nette dei giochi per il rimborso (si sposta solo quando il rimborso è pagato).
CREATE TABLE IF NOT EXISTS economia_rimborsi (
    guild_id  BIGINT NOT NULL,
    user_id   BIGINT NOT NULL,
    netto_base BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (guild_id, user_id)
);

CREATE TABLE IF NOT EXISTS economia_lotteria_biglietti (
    guild_id BIGINT  NOT NULL,
    giorno   DATE    NOT NULL,
    user_id  BIGINT  NOT NULL,
    biglietti INTEGER NOT NULL CHECK (biglietti > 0),
    spesa    BIGINT  NOT NULL CHECK (spesa > 0),
    PRIMARY KEY (guild_id, giorno, user_id)
);

CREATE TABLE IF NOT EXISTS economia_lotteria_estrazioni (
    id         BIGSERIAL PRIMARY KEY,
    guild_id   BIGINT NOT NULL,
    giorno     DATE   NOT NULL,
    vincitore  BIGINT NOT NULL,
    premio     BIGINT NOT NULL,
    partecipanti INTEGER NOT NULL,
    estratta_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (guild_id, giorno)
);
