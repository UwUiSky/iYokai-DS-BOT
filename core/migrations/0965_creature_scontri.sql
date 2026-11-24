-- #125 ECO-101: creature di fantasia comprate al negozio e scontri con posta in monete.
CREATE TABLE IF NOT EXISTS economia_creature (
    id          BIGSERIAL PRIMARY KEY,
    guild_id    BIGINT   NOT NULL,
    user_id     BIGINT   NOT NULL,
    specie      SMALLINT NOT NULL CHECK (specie BETWEEN 1 AND 8),
    forza       SMALLINT NOT NULL CHECK (forza BETWEEN 1 AND 90),
    vittorie    INTEGER  NOT NULL DEFAULT 0,
    sconfitte   INTEGER  NOT NULL DEFAULT 0,
    creata_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS economia_creature_utente ON economia_creature (guild_id, user_id);

CREATE TABLE IF NOT EXISTS economia_lotte_creature (
    id                    BIGSERIAL PRIMARY KEY,
    guild_id              BIGINT NOT NULL,
    vincitore             BIGINT NOT NULL,
    perdente              BIGINT NOT NULL,
    creatura_vincitrice   BIGINT NOT NULL,
    creatura_perdente     BIGINT NOT NULL,
    posta                 BIGINT NOT NULL CHECK (posta > 0),
    persa                 BOOLEAN NOT NULL DEFAULT FALSE,
    giocata_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (vincitore <> perdente)
);
CREATE INDEX IF NOT EXISTS economia_lotte_creature_server ON economia_lotte_creature (guild_id, vincitore);

-- Un oggetto del negozio può evocare una creatura: azione_valore è il numero della specie (1-8).
ALTER TABLE shop_items DROP CONSTRAINT IF EXISTS shop_items_azione_valida;
ALTER TABLE shop_items ADD CONSTRAINT shop_items_azione_valida
    CHECK (azione IN ('nessuna', 'monete', 'ruolo_dai', 'ruolo_togli', 'creatura')
           AND (azione = 'nessuna' OR azione_valore > 0)
           AND (azione <> 'creatura' OR azione_valore BETWEEN 1 AND 8));
