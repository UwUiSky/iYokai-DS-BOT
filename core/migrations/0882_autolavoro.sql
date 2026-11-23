-- ECO-050 (D121): lavoro automatico ogni 4 ore per chi lo accende (premium del server).
CREATE TABLE IF NOT EXISTS economia_autolavoro (
    guild_id     BIGINT NOT NULL,
    user_id      BIGINT NOT NULL,
    prossimo_at  TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (guild_id, user_id)
);
CREATE INDEX IF NOT EXISTS economia_autolavoro_prossimo ON economia_autolavoro (prossimo_at);
