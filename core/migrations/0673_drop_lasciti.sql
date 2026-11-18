-- #125 B4 (ECO-052, 053, 055): drop regolabili e monete lasciate in un canale.
ALTER TABLE leveling_settings
    ADD COLUMN IF NOT EXISTS drop_per_mille INTEGER NOT NULL DEFAULT 5,
    ADD COLUMN IF NOT EXISTS drop_min       INTEGER NOT NULL DEFAULT 10,
    ADD COLUMN IF NOT EXISTS drop_max       INTEGER NOT NULL DEFAULT 50,
    ADD COLUMN IF NOT EXISTS drop_pausa     INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS drop_canale_id BIGINT;

-- Monete lasciate da un utente: le prende il primo che clicca; se nessuno le prende tornano a chi le ha lasciate.
CREATE TABLE IF NOT EXISTS economia_lasciti (
    id         BIGSERIAL PRIMARY KEY,
    guild_id   BIGINT NOT NULL,
    user_id    BIGINT NOT NULL,
    importo    BIGINT NOT NULL CHECK (importo > 0),
    scade_at   TIMESTAMPTZ NOT NULL,
    preso_da   BIGINT,
    rimborsato BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE INDEX IF NOT EXISTS economia_lasciti_aperti ON economia_lasciti (scade_at) WHERE preso_da IS NULL AND NOT rimborsato;
