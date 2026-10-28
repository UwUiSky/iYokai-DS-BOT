-- #120 TKT-051/063/027/026: chiusura in due passi. Il ticket chiuso resta nel canale
-- (l'utente non lo vede più) con Riapri, Elimina e Transcript; il canale si elimina da
-- solo dopo N ore; si può spostare in una categoria dei chiusi; il nome può cambiare
-- alla presa in carico e alla chiusura.
ALTER TABLE ticket_panel_opzioni ADD COLUMN IF NOT EXISTS chiusura_due_passi BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE ticket_panel_opzioni ADD COLUMN IF NOT EXISTS elimina_dopo_ore INTEGER NOT NULL DEFAULT 0
    CHECK (elimina_dopo_ore BETWEEN 0 AND 720);
ALTER TABLE ticket_panel_opzioni ADD COLUMN IF NOT EXISTS categoria_chiusi BIGINT;
ALTER TABLE ticket_panel_opzioni ADD COLUMN IF NOT EXISTS prefisso_chiuso TEXT
    CHECK (prefisso_chiuso IS NULL OR char_length(prefisso_chiuso) BETWEEN 1 AND 20);
ALTER TABLE ticket_panel_opzioni ADD COLUMN IF NOT EXISTS prefisso_preso TEXT
    CHECK (prefisso_preso IS NULL OR char_length(prefisso_preso) BETWEEN 1 AND 20);
