-- #124 B2 (LIV-042, 047, 034): più ruoli per livello, avviso in DM, testo dell'annuncio;
-- XP di mese e settimana nelle copie di sicurezza (il ripristino li rimette).
ALTER TABLE level_reward_roles DROP CONSTRAINT IF EXISTS level_reward_roles_guild_id_level_threshold_key;
CREATE UNIQUE INDEX IF NOT EXISTS uq_level_reward_roles_ruolo
    ON level_reward_roles (guild_id, level_threshold, role_id);
ALTER TABLE level_reward_roles ADD COLUMN IF NOT EXISTS avvisa_dm BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE leveling_settings
    ADD COLUMN IF NOT EXISTS levelup_testo TEXT NOT NULL DEFAULT ''
        CHECK (char_length(levelup_testo) <= 1800);

CREATE TABLE IF NOT EXISTS leveling_copie_attivita (
    copia_id   BIGINT NOT NULL REFERENCES leveling_copie (id) ON DELETE CASCADE,
    user_id    BIGINT NOT NULL,
    period_key TEXT   NOT NULL,
    xp         BIGINT NOT NULL,
    PRIMARY KEY (copia_id, user_id, period_key)
);
CREATE INDEX IF NOT EXISTS idx_leveling_copie_attivita_utente ON leveling_copie_attivita (user_id);
