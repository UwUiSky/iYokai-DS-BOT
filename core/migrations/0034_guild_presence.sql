-- NF-04 (#75, #19, #46): quando il bot è entrato e uscito da ogni server.
-- `left_at` avvia i 90 giorni (D6); se il bot rientra prima, `left_at` torna NULL
-- e non si perde niente. `purged_at` dice che i dati del server sono già stati
-- cancellati dal lavoro giornaliero (core/retention_worker.py).
CREATE TABLE IF NOT EXISTS guild_presence (
    guild_id   BIGINT PRIMARY KEY,
    joined_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    left_at    TIMESTAMPTZ,
    purged_at  TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_guild_presence_usciti
    ON guild_presence (left_at) WHERE left_at IS NOT NULL AND purged_at IS NULL;

-- I server già nel database prima di questa migrazione sono "presenti": il bot li
-- riconosce all'avvio e, se non ci sono più, avvia il conto dei 90 giorni.
INSERT INTO guild_presence (guild_id, joined_at)
    SELECT guild_id, created_at FROM guild_config
    ON CONFLICT (guild_id) DO NOTHING;
