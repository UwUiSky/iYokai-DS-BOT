-- CFG-038 (#122): codici premium da riscattare, a tempo o permanenti.
-- Il codice in chiaro si mostra una volta sola all'owner; qui resta solo l'impronta (sha256).
-- Registro contabile: si conserva anche se la persona chiede la cancellazione (core/data_registry.py).
CREATE TABLE IF NOT EXISTS premium_codes (
    code_hash         TEXT PRIMARY KEY,
    code_hint         TEXT NOT NULL,
    module_name       TEXT,
    duration_days     INTEGER NOT NULL CHECK (duration_days > 0),
    created_by        BIGINT NOT NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    redeemed_by       BIGINT,
    redeemed_guild_id BIGINT,
    redeemed_at       TIMESTAMPTZ
);
