-- Motore AI (#95, SPEC §25.23): inizio della prova gratuita per server, una volta sola.
-- Tabella a parte che resta anche quando i dati del server si cancellano (90 giorni
-- dopo l'uscita): togliere e rimettere il bot non fa ripartire la prova.
CREATE TABLE IF NOT EXISTS ai_prove (
    guild_id BIGINT PRIMARY KEY,
    inizio   TIMESTAMPTZ NOT NULL DEFAULT now()
);
INSERT INTO ai_prove (guild_id, inizio)
SELECT guild_id, prova_inizio FROM ai_config WHERE prova_inizio IS NOT NULL
ON CONFLICT (guild_id) DO NOTHING;
