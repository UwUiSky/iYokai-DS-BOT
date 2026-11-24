-- FUN-075 (D127, D129): suoni della soundboard usati da altri server. Di base un server NON mette a disposizione i suoi
-- suoni (condividi = FALSE) e i suoi membri possono usare quelli degli altri (usa_esterni = TRUE).
CREATE TABLE IF NOT EXISTS suoni_condivisione (
    guild_id     BIGINT PRIMARY KEY,
    condividi    BOOLEAN NOT NULL DEFAULT FALSE,
    usa_esterni  BOOLEAN NOT NULL DEFAULT TRUE,
    aggiornato   TIMESTAMPTZ NOT NULL DEFAULT now()
);
