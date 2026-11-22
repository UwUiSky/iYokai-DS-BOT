-- #120: aspetto dei pannelli e campi del modulo.
-- TKT-004: colore del bottone. TKT-005: segnaposto del menu dei motivi e descrizione di ogni voce
-- (motivi e categorie). TKT-036: embed salvato dal costruttore come messaggio di apertura del ticket.
-- TKT-011: minimo e massimo di caratteri di una risposta. TKT-012: campi a scelta (menu, utente, ruolo, canale).
ALTER TABLE ticket_panels ADD COLUMN IF NOT EXISTS button_style VARCHAR(12) NOT NULL DEFAULT 'primary';
ALTER TABLE ticket_panels DROP CONSTRAINT IF EXISTS ticket_panels_button_style_check;
ALTER TABLE ticket_panels ADD CONSTRAINT ticket_panels_button_style_check
    CHECK (button_style IN ('primary', 'secondary', 'success', 'danger'));
ALTER TABLE ticket_panels ADD COLUMN IF NOT EXISTS menu_segnaposto VARCHAR(150);
ALTER TABLE ticket_panels ADD COLUMN IF NOT EXISTS embed_apertura VARCHAR(32);
ALTER TABLE ticket_panel_motivi ADD COLUMN IF NOT EXISTS descrizione VARCHAR(100);
ALTER TABLE ticket_categories ADD COLUMN IF NOT EXISTS descrizione VARCHAR(100);

ALTER TABLE ticket_form_questions ADD COLUMN IF NOT EXISTS min_length SMALLINT
    CHECK (min_length IS NULL OR min_length BETWEEN 0 AND 4000);
ALTER TABLE ticket_form_questions ADD COLUMN IF NOT EXISTS max_length SMALLINT
    CHECK (max_length IS NULL OR max_length BETWEEN 1 AND 4000);
ALTER TABLE ticket_form_questions ADD COLUMN IF NOT EXISTS tipo VARCHAR(10) NOT NULL DEFAULT 'testo'
    CHECK (tipo IN ('testo', 'scelta', 'utente', 'ruolo', 'canale'));
ALTER TABLE ticket_form_questions ADD COLUMN IF NOT EXISTS opzioni TEXT[] NOT NULL DEFAULT '{}';
ALTER TABLE ticket_form_questions ADD COLUMN IF NOT EXISTS max_valori SMALLINT NOT NULL DEFAULT 1
    CHECK (max_valori BETWEEN 1 AND 25);
