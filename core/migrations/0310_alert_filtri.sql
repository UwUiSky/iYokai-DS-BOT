-- #129 (ALR-030, 031, 032, 033, 036): pausa, filtri su titolo e gioco, pausa minima tra due avvisi.
ALTER TABLE alert_options ADD COLUMN IF NOT EXISTS paused            BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE alert_options ADD COLUMN IF NOT EXISTS title_words       TEXT NOT NULL DEFAULT '';
ALTER TABLE alert_options ADD COLUMN IF NOT EXISTS game_filter       TEXT NOT NULL DEFAULT '';
ALTER TABLE alert_options ADD COLUMN IF NOT EXISTS min_gap_minutes   INTEGER NOT NULL DEFAULT 0;
ALTER TABLE alert_options ADD COLUMN IF NOT EXISTS last_published_at TIMESTAMPTZ;
