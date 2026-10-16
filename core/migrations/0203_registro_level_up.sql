-- LIV-039 (#124): gli ultimi level-up di ogni server, per /level livelli-recenti.
-- Si tengono solo le 25 righe più recenti per server (le altre le cancella
-- chi scrive), quindi la tabella non cresce.
CREATE TABLE IF NOT EXISTS leveling_levelup_log (
    id         BIGSERIAL PRIMARY KEY,
    guild_id   BIGINT NOT NULL,
    user_id    BIGINT NOT NULL,
    livello    INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS leveling_levelup_log_server ON leveling_levelup_log (guild_id, id DESC);
