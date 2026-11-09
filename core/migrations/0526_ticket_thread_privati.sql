-- TKT-031 / TKT-032: ticket come thread privati. Per pannello: tipo (canale o thread), canale padre dei thread
-- e canale degli avvisi con il bottone «Entra» per lo staff. Per ticket: è un thread?
ALTER TABLE ticket_panel_opzioni ADD COLUMN IF NOT EXISTS tipo VARCHAR(8) NOT NULL DEFAULT 'canale'
    CHECK (tipo IN ('canale', 'thread'));
ALTER TABLE ticket_panel_opzioni ADD COLUMN IF NOT EXISTS canale_padre_id BIGINT;
ALTER TABLE ticket_panel_opzioni ADD COLUMN IF NOT EXISTS canale_avvisi_id BIGINT;
ALTER TABLE tickets ADD COLUMN IF NOT EXISTS e_thread BOOLEAN NOT NULL DEFAULT FALSE;
