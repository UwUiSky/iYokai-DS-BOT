-- #125 B6 (ECO-004, 029, 030, 031, 032, 040, 041): banca, pause dei guadagni, colpo e furto.
ALTER TABLE leveling_totals ADD COLUMN IF NOT EXISTS banca_total BIGINT NOT NULL DEFAULT 0 CHECK (banca_total >= 0);
ALTER TABLE leveling_settings
    ADD COLUMN IF NOT EXISTS furto_attivo     BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS furto_percentuale INTEGER NOT NULL DEFAULT 10,
    ADD COLUMN IF NOT EXISTS furto_successo   INTEGER NOT NULL DEFAULT 40,
    ADD COLUMN IF NOT EXISTS colpo_successo   INTEGER NOT NULL DEFAULT 40;

-- Una pausa per persona e per azione (colpo, furto, elemosina...): si prende con una scrittura condizionata.
CREATE TABLE IF NOT EXISTS economia_pause (
    guild_id  BIGINT NOT NULL,
    user_id   BIGINT NOT NULL,
    chiave    TEXT   NOT NULL,
    ultima_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (guild_id, user_id, chiave)
);

-- Turni di lavoro fatti (scala dei lavori, ECO-029).
CREATE TABLE IF NOT EXISTS economia_lavoro (
    guild_id BIGINT NOT NULL,
    user_id  BIGINT NOT NULL,
    turni    INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (guild_id, user_id)
);
