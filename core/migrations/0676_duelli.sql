-- #125 B7 (ECO-104, 106): storico dei duelli con posta in monete.
CREATE TABLE IF NOT EXISTS economia_duelli (
    id          BIGSERIAL PRIMARY KEY,
    guild_id    BIGINT NOT NULL,
    vincitore   BIGINT NOT NULL,
    perdente    BIGINT NOT NULL,
    posta       BIGINT NOT NULL CHECK (posta > 0),
    giocato_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (vincitore <> perdente)
);
CREATE INDEX IF NOT EXISTS economia_duelli_server ON economia_duelli (guild_id, vincitore);
CREATE INDEX IF NOT EXISTS economia_duelli_perdente ON economia_duelli (guild_id, perdente);
