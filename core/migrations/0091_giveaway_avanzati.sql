-- #99 (NF-28): giveaway avanzati. Requisito sui messaggi (contati dall'inizio
-- del giveaway), ruolo che salta i requisiti, ingressi extra per un ruolo,
-- giveaway programmati e modelli riusabili.
ALTER TABLE giveaways
    ADD COLUMN IF NOT EXISTS min_messages     INT     NOT NULL DEFAULT 0 CHECK (min_messages BETWEEN 0 AND 100000),
    ADD COLUMN IF NOT EXISTS bypass_role_id   BIGINT,
    ADD COLUMN IF NOT EXISTS bonus_role_id    BIGINT,
    ADD COLUMN IF NOT EXISTS bonus_entries    INT     NOT NULL DEFAULT 0 CHECK (bonus_entries BETWEEN 0 AND 20),
    ADD COLUMN IF NOT EXISTS starts_at        TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS started          BOOLEAN NOT NULL DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS duration_seconds INT;

-- Chi non è ancora partito non ha né messaggio né scadenza reale.
CREATE INDEX IF NOT EXISTS idx_giveaways_da_avviare
    ON giveaways (starts_at) WHERE started = false AND ended = false;

ALTER TABLE giveaway_entries
    ADD COLUMN IF NOT EXISTS tickets INT NOT NULL DEFAULT 1 CHECK (tickets BETWEEN 1 AND 21);

-- Messaggi scritti da ciascuno mentre il giveaway è aperto. Si toglie con il giveaway.
CREATE TABLE IF NOT EXISTS giveaway_message_counts (
    giveaway_id INT    NOT NULL REFERENCES giveaways (id) ON DELETE CASCADE,
    user_id     BIGINT NOT NULL,
    n           INT    NOT NULL DEFAULT 0,
    PRIMARY KEY (giveaway_id, user_id)
);

CREATE TABLE IF NOT EXISTS giveaway_templates (
    guild_id         BIGINT NOT NULL,
    name             TEXT   NOT NULL CHECK (char_length(name) BETWEEN 1 AND 32),
    prize            TEXT   NOT NULL CHECK (char_length(prize) BETWEEN 1 AND 200),
    winners_count    INT    NOT NULL DEFAULT 1 CHECK (winners_count BETWEEN 1 AND 50),
    duration_minutes INT    NOT NULL CHECK (duration_minutes BETWEEN 1 AND 43200),
    min_level        INT    NOT NULL DEFAULT 0,
    required_role_id BIGINT,
    min_messages     INT    NOT NULL DEFAULT 0 CHECK (min_messages BETWEEN 0 AND 100000),
    bypass_role_id   BIGINT,
    bonus_role_id    BIGINT,
    bonus_entries    INT    NOT NULL DEFAULT 0 CHECK (bonus_entries BETWEEN 0 AND 20),
    PRIMARY KEY (guild_id, name)
);
