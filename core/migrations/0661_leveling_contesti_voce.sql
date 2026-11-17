-- #124 B4 (LIV-011, 012, 014, 015, 016): soglia di persone e anti-farm in vocale, XP nei thread,
-- nei post dei forum e nella chat dei canali vocali (di base come prima: acceso, soglia 2).
ALTER TABLE leveling_settings
    ADD COLUMN IF NOT EXISTS voce_min_persone INTEGER NOT NULL DEFAULT 2
        CHECK (voce_min_persone BETWEEN 1 AND 10),
    ADD COLUMN IF NOT EXISTS anti_farm BOOLEAN NOT NULL DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS xp_thread BOOLEAN NOT NULL DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS xp_forum BOOLEAN NOT NULL DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS xp_chat_vocale BOOLEAN NOT NULL DEFAULT TRUE;
