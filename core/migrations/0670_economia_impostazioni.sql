-- #125 B1 (ECO-002, 003, 014, 019, 021, 022, 024, 025, 026, 028): regole dell'economia scelte dal server.
ALTER TABLE leveling_settings
    ADD COLUMN IF NOT EXISTS saldo_iniziale     BIGINT   NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS tetto_saldo        BIGINT   NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS puntata_min        INTEGER  NOT NULL DEFAULT 1,
    ADD COLUMN IF NOT EXISTS puntata_max        INTEGER  NOT NULL DEFAULT 10000,
    ADD COLUMN IF NOT EXISTS attesa_gioco       INTEGER  NOT NULL DEFAULT 5,
    ADD COLUMN IF NOT EXISTS daily_ore          INTEGER  NOT NULL DEFAULT 24,
    ADD COLUMN IF NOT EXISTS work_attesa_min    INTEGER  NOT NULL DEFAULT 60,
    ADD COLUMN IF NOT EXISTS daily_bonus_serie  INTEGER  NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS daily_serie_max    INTEGER  NOT NULL DEFAULT 30,
    ADD COLUMN IF NOT EXISTS settimanale_coins  INTEGER  NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS mensile_coins      INTEGER  NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS saldo_uscita       TEXT     NOT NULL DEFAULT 'tieni';

-- Il saldo di partenza si dà una volta sola per persona e per server.
CREATE TABLE IF NOT EXISTS economia_accrediti_iniziali (
    guild_id BIGINT NOT NULL,
    user_id  BIGINT NOT NULL,
    dato_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (guild_id, user_id)
);

-- Premi settimanale e mensile: l'ultima riscossione, scritta nella stessa istruzione che paga.
CREATE TABLE IF NOT EXISTS economia_premi_periodici (
    guild_id  BIGINT NOT NULL,
    user_id   BIGINT NOT NULL,
    tipo      TEXT   NOT NULL CHECK (tipo IN ('settimanale', 'mensile')),
    ultima_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (guild_id, user_id, tipo)
);

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'puntata_ordine') THEN
        ALTER TABLE leveling_settings ADD CONSTRAINT puntata_ordine CHECK (puntata_min <= puntata_max);
    END IF;
END $$;
