-- TKT-071 / TKT-074: formato del transcript (testo, html, entrambi) e ZIP delle immagini controllate.
ALTER TABLE ticket_panel_opzioni ADD COLUMN IF NOT EXISTS transcript_formato VARCHAR(10) NOT NULL DEFAULT 'testo'
    CHECK (transcript_formato IN ('testo', 'html', 'entrambi'));
ALTER TABLE ticket_panel_opzioni ADD COLUMN IF NOT EXISTS allegati_zip BOOLEAN NOT NULL DEFAULT FALSE;
