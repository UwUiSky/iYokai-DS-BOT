-- D69 B6: fuso personale (menu «Orari nel mio fuso»), iscritti a un promemoria pubblico (massimo 25) e chi ha
-- registrato il compleanno di un altro membro (staff).
CREATE TABLE IF NOT EXISTS utente_fuso (
    user_id BIGINT PRIMARY KEY,
    fuso    TEXT NOT NULL CHECK (char_length(fuso) BETWEEN 1 AND 60)
);
CREATE TABLE IF NOT EXISTS promemoria_iscritti (
    serie     TEXT NOT NULL CHECK (char_length(serie) <= 32),
    guild_id  BIGINT NOT NULL,
    user_id   BIGINT NOT NULL,
    creato_il TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (serie, user_id)
);
CREATE INDEX IF NOT EXISTS idx_promemoria_iscritti_server ON promemoria_iscritti (guild_id);
ALTER TABLE birthdays ADD COLUMN IF NOT EXISTS inserito_da BIGINT;
