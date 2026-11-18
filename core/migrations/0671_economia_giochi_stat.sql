-- #125 B2 (ECO-115, ECO-116): conteggi e vincite più grosse dei giochi con le monete.
CREATE TABLE IF NOT EXISTS economia_giochi_stat (
    guild_id     BIGINT NOT NULL,
    user_id      BIGINT NOT NULL,
    gioco        TEXT   NOT NULL,
    partite      INTEGER NOT NULL DEFAULT 0,
    vinte        INTEGER NOT NULL DEFAULT 0,
    perse        INTEGER NOT NULL DEFAULT 0,
    pari         INTEGER NOT NULL DEFAULT 0,
    puntato      BIGINT NOT NULL DEFAULT 0,
    netto        BIGINT NOT NULL DEFAULT 0,
    max_vincita  BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (guild_id, user_id, gioco)
);
CREATE INDEX IF NOT EXISTS economia_giochi_stat_record ON economia_giochi_stat (guild_id, max_vincita DESC);
