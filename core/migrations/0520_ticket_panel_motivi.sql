-- TKT-006: motivi pronti per pannello. Chi apre il ticket sceglie un motivo (o «Altro»).
-- Al massimo 24 per pannello (+ «Altro» = 25 voci del menu di Discord).
CREATE TABLE IF NOT EXISTS ticket_panel_motivi (
    id        SERIAL PRIMARY KEY,
    panel_id  INTEGER NOT NULL REFERENCES ticket_panels(id) ON DELETE CASCADE,
    posizione SMALLINT NOT NULL CHECK (posizione BETWEEN 1 AND 24),
    etichetta VARCHAR(80) NOT NULL,
    emoji     VARCHAR(64),
    testo     VARCHAR(512),
    UNIQUE (panel_id, posizione) DEFERRABLE INITIALLY DEFERRED
);
