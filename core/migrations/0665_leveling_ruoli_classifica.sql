-- #124 B8 (LIV-044, 045): ruoli dati a chi sta in cima alla classifica (primo, primi 3, primi 10).
CREATE TABLE IF NOT EXISTS leveling_ruoli_classifica (
    guild_id BIGINT   NOT NULL,
    fascia   SMALLINT NOT NULL CHECK (fascia IN (1, 3, 10)),
    role_id  BIGINT   NOT NULL,
    PRIMARY KEY (guild_id, fascia)
);
