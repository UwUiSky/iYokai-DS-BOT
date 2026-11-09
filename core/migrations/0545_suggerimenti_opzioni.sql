-- D69 B7: opzioni dei suggerimenti per server (anonimi, colore a soglia di voti, canale unico, esito) e il
-- segno «anonimo» su ogni suggerimento (vale com'era quando è stato scritto).
CREATE TABLE IF NOT EXISTS suggestions_config (
    guild_id      BIGINT PRIMARY KEY,
    anonimi       BOOLEAN NOT NULL DEFAULT FALSE,
    soglia        INT NOT NULL DEFAULT 0 CHECK (soglia BETWEEN 0 AND 10000),
    colore        TEXT CHECK (colore IS NULL OR colore ~ '^#[0-9A-Fa-f]{6}$'),
    solo_canale_id BIGINT,
    esito         TEXT NOT NULL DEFAULT 'modifica' CHECK (esito IN ('modifica', 'nuovo'))
);
ALTER TABLE suggestions ADD COLUMN IF NOT EXISTS anonimo BOOLEAN NOT NULL DEFAULT FALSE;
