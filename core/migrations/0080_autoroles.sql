-- NF-07 (#78): ruoli automatici all'ingresso, ruoli ridati a chi rientra.
CREATE TABLE IF NOT EXISTS autorole_rules (
    guild_id      BIGINT NOT NULL,
    role_id       BIGINT NOT NULL,
    delay_seconds INTEGER NOT NULL DEFAULT 0 CHECK (delay_seconds BETWEEN 0 AND 604800),
    created_by    BIGINT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (guild_id, role_id)
);

CREATE TABLE IF NOT EXISTS autorole_config (
    guild_id         BIGINT PRIMARY KEY,
    remember_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    remember_days    INTEGER NOT NULL DEFAULT 30 CHECK (remember_days BETWEEN 1 AND 30)
);

-- Ruoli di chi esce, per ridarli se rientra entro remember_days (al massimo 30).
CREATE TABLE IF NOT EXISTS autorole_memory (
    guild_id BIGINT NOT NULL,
    user_id  BIGINT NOT NULL,
    role_ids BIGINT[] NOT NULL,
    left_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (guild_id, user_id)
);
