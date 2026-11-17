-- #124 B3 (LIV-004, 006, 007, 017, 018, 021): formula dei livelli, XP a parola, bonus impegno,
-- XP dei comandi, prefissi di altri bot, elenco bianco dei canali.
ALTER TABLE leveling_settings
    ADD COLUMN IF NOT EXISTS formula TEXT NOT NULL DEFAULT 'classica'
        CHECK (formula IN ('classica', 'lineare', 'esponenziale', 'costante')),
    ADD COLUMN IF NOT EXISTS xp_modo TEXT NOT NULL DEFAULT 'fisso'
        CHECK (xp_modo IN ('fisso', 'parola')),
    ADD COLUMN IF NOT EXISTS xp_per_parola INTEGER NOT NULL DEFAULT 1
        CHECK (xp_per_parola BETWEEN 1 AND 10),
    ADD COLUMN IF NOT EXISTS parole_max INTEGER NOT NULL DEFAULT 30
        CHECK (parole_max BETWEEN 1 AND 100),
    ADD COLUMN IF NOT EXISTS bonus_impegno INTEGER NOT NULL DEFAULT 0
        CHECK (bonus_impegno BETWEEN 0 AND 50),
    ADD COLUMN IF NOT EXISTS impegno_caratteri INTEGER NOT NULL DEFAULT 200
        CHECK (impegno_caratteri BETWEEN 20 AND 2000),
    ADD COLUMN IF NOT EXISTS xp_comandi BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS prefissi_ignorati TEXT[] NOT NULL DEFAULT '{}'
        CHECK (cardinality(prefissi_ignorati) <= 10),
    ADD COLUMN IF NOT EXISTS canali_modo TEXT NOT NULL DEFAULT 'tutti'
        CHECK (canali_modo IN ('tutti', 'solo_questi'));
