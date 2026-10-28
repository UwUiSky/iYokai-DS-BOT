-- #127: aspetto del pannello dei vocali temporanei (VOC-010) e canali
-- copiati dal canale generatore (VOC-013).
ALTER TABLE voice_temp_config ADD COLUMN IF NOT EXISTS pannello_titolo TEXT
    CHECK (pannello_titolo IS NULL OR char_length(pannello_titolo) BETWEEN 1 AND 256);
ALTER TABLE voice_temp_config ADD COLUMN IF NOT EXISTS pannello_testo TEXT
    CHECK (pannello_testo IS NULL OR char_length(pannello_testo) BETWEEN 1 AND 1000);
ALTER TABLE voice_temp_config ADD COLUMN IF NOT EXISTS pannello_colore INTEGER
    CHECK (pannello_colore IS NULL OR pannello_colore BETWEEN 0 AND 16777215);
ALTER TABLE voice_temp_config ADD COLUMN IF NOT EXISTS clona_generatore BOOLEAN NOT NULL DEFAULT false;
