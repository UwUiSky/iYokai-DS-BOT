-- NF-22 (#93): abbonamenti Discord (app premium) che sbloccano il premium di un server.
-- Una riga per diritto (`entitlement`) di Discord. I pagamenti esterni restano in `module_subscriptions`
-- (l'owner li concede con /owner premium grant). Registro contabile: si conserva anche se la persona
-- chiede la cancellazione dei dati (core/data_registry.py).
CREATE TABLE IF NOT EXISTS premium_entitlements (
    entitlement_id BIGINT PRIMARY KEY,
    guild_id       BIGINT NOT NULL,
    user_id        BIGINT,
    sku_id         BIGINT NOT NULL,
    starts_at      TIMESTAMPTZ,
    ends_at        TIMESTAMPTZ,
    deleted        BOOLEAN NOT NULL DEFAULT FALSE,
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_premium_entitlements_guild ON premium_entitlements (guild_id) WHERE NOT deleted;
