-- #124 B7 (LIV-001, 002, 003): XP minimo e massimo per messaggio, pausa fino a un'ora,
-- velocità generale (percentuale) applicata a ogni guadagno.
ALTER TABLE leveling_settings DROP CONSTRAINT IF EXISTS leveling_settings_text_cooldown_seconds_check;
ALTER TABLE leveling_settings
    ADD CONSTRAINT leveling_settings_text_cooldown_seconds_check
        CHECK (text_cooldown_seconds BETWEEN 10 AND 3600);
ALTER TABLE leveling_settings
    ADD COLUMN IF NOT EXISTS text_xp_max INTEGER NOT NULL DEFAULT 0
        CHECK (text_xp_max BETWEEN 0 AND 100),
    ADD COLUMN IF NOT EXISTS xp_percentuale INTEGER NOT NULL DEFAULT 100
        CHECK (xp_percentuale BETWEEN 25 AND 500);
