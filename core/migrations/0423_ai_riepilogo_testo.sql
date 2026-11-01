-- NF-24 (r12): ultimo riepilogo pubblicato, per la pagina AI del pannello (AI-R-099).
ALTER TABLE ai_riepiloghi ADD COLUMN IF NOT EXISTS ultimo_testo TEXT;
