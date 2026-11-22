-- Catalogo #115 (MOD-091, 092, 094, 095, 096): blocco di canali scelti o di un gruppo, blocco «cieco», kick o ban
-- di chi entra, permessi dei ruoli tolti e rimessi.
ALTER TABLE lockdown_stato ADD COLUMN IF NOT EXISTS opzioni TEXT NOT NULL DEFAULT '{}';  -- JSON: nascosto, ingressi, avviso, ruoli, solo_canali
ALTER TABLE lockdown_config ADD COLUMN IF NOT EXISTS gruppo_canali BIGINT[] NOT NULL DEFAULT '{}';
ALTER TABLE lockdown_config DROP CONSTRAINT IF EXISTS lockdown_config_gruppo_check;
ALTER TABLE lockdown_config ADD CONSTRAINT lockdown_config_gruppo_check CHECK (cardinality(gruppo_canali) <= 25);
CREATE TABLE IF NOT EXISTS lockdown_ruoli (
    guild_id      BIGINT  NOT NULL,
    role_id       BIGINT  NOT NULL,
    tolti         BIGINT  NOT NULL,   -- i bit dei permessi che il blocco ha tolto
    ripristinato  BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (guild_id, role_id)
);
