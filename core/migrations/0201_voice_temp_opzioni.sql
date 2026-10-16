-- #127: opzioni dei vocali temporanei per server.
-- VOC-011/012 nome da modello ({utente}, {numero}); VOC-015 canali che
-- nascono bloccati; VOC-018 canale di registro delle azioni.
ALTER TABLE voice_temp_config ADD COLUMN IF NOT EXISTS nome_modello TEXT
    CHECK (nome_modello IS NULL OR char_length(nome_modello) BETWEEN 1 AND 90);
ALTER TABLE voice_temp_config ADD COLUMN IF NOT EXISTS nasce_bloccato BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE voice_temp_config ADD COLUMN IF NOT EXISTS canale_registro_id BIGINT;
-- Numero del canale nella sequenza del server (Stanza 1, Stanza 2…).
ALTER TABLE voice_temp_channels ADD COLUMN IF NOT EXISTS numero INTEGER;
