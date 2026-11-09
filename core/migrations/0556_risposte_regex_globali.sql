-- D69 B18: risposte automatiche con espressione regolare e «inizia con» (trigger fino a 200 caratteri),
-- risposte globali dell'owner (max 20, ogni server le può spegnere).
ALTER TABLE autoresponders DROP CONSTRAINT IF EXISTS autoresponders_match_mode_check;
ALTER TABLE autoresponders ADD CONSTRAINT autoresponders_match_mode_check
    CHECK (match_mode IN ('esatta', 'parziale', 'inizia', 'regex'));
ALTER TABLE autoresponders DROP CONSTRAINT IF EXISTS autoresponders_trigger_check;
ALTER TABLE autoresponders ADD CONSTRAINT autoresponders_trigger_check CHECK (char_length(trigger) BETWEEN 1 AND 200);

CREATE TABLE IF NOT EXISTS autorisposte_globali (
    id        SERIAL PRIMARY KEY,
    innesco   TEXT NOT NULL CHECK (char_length(innesco) BETWEEN 1 AND 100),
    risposta  TEXT NOT NULL CHECK (char_length(risposta) BETWEEN 1 AND 1000),
    creata_da BIGINT,
    creata_il TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_autorisposte_globali_innesco ON autorisposte_globali (lower(innesco));

CREATE TABLE IF NOT EXISTS autorisposte_server (
    guild_id       BIGINT PRIMARY KEY,
    globali_spente BOOLEAN NOT NULL DEFAULT FALSE
);
