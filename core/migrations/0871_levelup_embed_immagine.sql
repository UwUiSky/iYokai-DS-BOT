-- r1rep (LIV-032, LIV-033): annuncio del level-up dentro un embed salvato e con una piccola immagine.
ALTER TABLE leveling_settings
    ADD COLUMN IF NOT EXISTS levelup_embed TEXT NOT NULL DEFAULT '' CHECK (char_length(levelup_embed) <= 32),
    ADD COLUMN IF NOT EXISTS levelup_immagine BOOLEAN NOT NULL DEFAULT FALSE;
