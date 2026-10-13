-- #111 (NF-40): gioco del conteggio. Un canale per server dove si conta
-- 1, 2, 3... a turno; chi sbaglia riporta il conteggio a zero. Tiene solo
-- l'ultimo numero, chi ha contato per ultimo (per non contare due volte di
-- fila) e il record.
CREATE TABLE IF NOT EXISTS counting_games (
    guild_id     BIGINT PRIMARY KEY,
    channel_id   BIGINT NOT NULL,
    current      INT    NOT NULL DEFAULT 0 CHECK (current >= 0),
    last_user_id BIGINT,
    best         INT    NOT NULL DEFAULT 0 CHECK (best >= 0)
);
