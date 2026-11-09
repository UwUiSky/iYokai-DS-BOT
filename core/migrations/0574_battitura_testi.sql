-- #131 B7 (D70): testi di battitura scritti dal server (al massimo 50 per server, 300 caratteri l'uno).
CREATE TABLE IF NOT EXISTS battitura_testi (
    id        BIGSERIAL PRIMARY KEY,
    guild_id  BIGINT NOT NULL,
    testo     TEXT NOT NULL CHECK (char_length(testo) <= 300),
    autore_id BIGINT NOT NULL,
    creato    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_battitura_testi ON battitura_testi (guild_id, id);
