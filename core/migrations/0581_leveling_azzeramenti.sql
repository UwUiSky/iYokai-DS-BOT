-- #124 B1 (LIV-068..071): copie di sicurezza degli XP, azzeramento automatico
-- di chi esce o viene bannato, blocco dei comandi di XP al proprietario del server.
ALTER TABLE leveling_settings
    ADD COLUMN IF NOT EXISTS azzera_su TEXT NOT NULL DEFAULT 'nessuno'
        CHECK (azzera_su IN ('nessuno', 'uscita', 'ban', 'entrambi')),
    ADD COLUMN IF NOT EXISTS copia_su_uscita BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS blocca_xp BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS blocca_azzeramento BOOLEAN NOT NULL DEFAULT FALSE;

CREATE TABLE IF NOT EXISTS leveling_copie (
    id        BIGSERIAL PRIMARY KEY,
    guild_id  BIGINT      NOT NULL,
    tipo      TEXT        NOT NULL CHECK (tipo IN ('server', 'utente')),
    creata_il TIMESTAMPTZ NOT NULL DEFAULT now(),
    scade_il  TIMESTAMPTZ NOT NULL,
    autore_id BIGINT,
    motivo    TEXT        NOT NULL DEFAULT '' CHECK (char_length(motivo) <= 512),
    righe     INT         NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_leveling_copie_server ON leveling_copie (guild_id, creata_il DESC);
CREATE INDEX IF NOT EXISTS idx_leveling_copie_scadenza ON leveling_copie (scade_il);

CREATE TABLE IF NOT EXISTS leveling_copie_righe (
    copia_id BIGINT NOT NULL REFERENCES leveling_copie (id) ON DELETE CASCADE,
    user_id  BIGINT NOT NULL,
    xp_total BIGINT NOT NULL,
    level    INT    NOT NULL,
    PRIMARY KEY (copia_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_leveling_copie_righe_utente ON leveling_copie_righe (user_id);
