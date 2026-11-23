-- FUN-019 (D111, #131): battaglia a turni tra due utenti. Statistiche vinte e perse per server.
CREATE TABLE IF NOT EXISTS fun_battaglie_stat (
    guild_id  BIGINT NOT NULL,
    user_id   BIGINT NOT NULL,
    vinte     INTEGER NOT NULL DEFAULT 0 CHECK (vinte >= 0),
    perse     INTEGER NOT NULL DEFAULT 0 CHECK (perse >= 0),
    PRIMARY KEY (guild_id, user_id)
);
