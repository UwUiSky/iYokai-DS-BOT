-- #127 VOC-016: altri canali generatori nello stesso server, ognuno con
-- la sua categoria, il suo modello di nome e il suo limite di utenti.
-- Il generatore principale resta in voice_temp_config.
CREATE TABLE IF NOT EXISTS voice_temp_generatori (
    channel_id    BIGINT PRIMARY KEY,
    guild_id      BIGINT NOT NULL,
    category_id   BIGINT NOT NULL,
    nome_modello  TEXT CHECK (nome_modello IS NULL OR char_length(nome_modello) BETWEEN 1 AND 90),
    limite_utenti INTEGER NOT NULL DEFAULT 0 CHECK (limite_utenti BETWEEN 0 AND 99),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_voice_temp_generatori_guild ON voice_temp_generatori (guild_id);
