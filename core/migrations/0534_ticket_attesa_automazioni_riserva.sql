-- TKT-029 (categoria «in attesa dell'utente»), TKT-064 (regole di inattività), TKT-035 (riserva di canali).
ALTER TABLE ticket_panel_opzioni ADD COLUMN IF NOT EXISTS attesa_categoria_id BIGINT;
ALTER TABLE ticket_panel_opzioni ADD COLUMN IF NOT EXISTS attesa_minuti INTEGER NOT NULL DEFAULT 0
    CHECK (attesa_minuti BETWEEN 0 AND 43200);
ALTER TABLE ticket_panel_opzioni ADD COLUMN IF NOT EXISTS riserva_canali INTEGER NOT NULL DEFAULT 0
    CHECK (riserva_canali BETWEEN 0 AND 5);

-- Chi ha scritto per ultimo nel ticket e lo spostamento nella categoria «in attesa».
ALTER TABLE tickets ADD COLUMN IF NOT EXISTS ultimo_utente_at TIMESTAMPTZ;
ALTER TABLE tickets ADD COLUMN IF NOT EXISTS ultimo_staff_at TIMESTAMPTZ;
ALTER TABLE tickets ADD COLUMN IF NOT EXISTS in_attesa_da TIMESTAMPTZ;
ALTER TABLE tickets ADD COLUMN IF NOT EXISTS categoria_prima_attesa BIGINT;
ALTER TABLE tickets ADD COLUMN IF NOT EXISTS spostato_at TIMESTAMPTZ;

-- Al massimo 5 regole per pannello (controllato dal codice); minimo 5 minuti.
CREATE TABLE IF NOT EXISTS ticket_automazioni (
    id       SERIAL PRIMARY KEY,
    panel_id INTEGER NOT NULL REFERENCES ticket_panels(id) ON DELETE CASCADE,
    chi      VARCHAR(10) NOT NULL CHECK (chi IN ('utente', 'staff', 'chiunque')),
    minuti   INTEGER NOT NULL CHECK (minuti BETWEEN 5 AND 43200),
    azione   VARCHAR(10) NOT NULL CHECK (azione IN ('chiudi', 'elimina', 'messaggio')),
    testo    VARCHAR(1000),
    ripeti   BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE INDEX IF NOT EXISTS idx_ticket_automazioni_pannello ON ticket_automazioni (panel_id);
CREATE TABLE IF NOT EXISTS ticket_automazioni_eseguite (
    ticket_id     INTEGER NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
    automazione_id INTEGER NOT NULL REFERENCES ticket_automazioni(id) ON DELETE CASCADE,
    ultima_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (ticket_id, automazione_id)
);

-- Canali vuoti già pronti per i pannelli (0-5 per pannello).
CREATE TABLE IF NOT EXISTS ticket_riserva (
    channel_id BIGINT PRIMARY KEY,
    guild_id   BIGINT NOT NULL,
    panel_id   INTEGER NOT NULL REFERENCES ticket_panels(id) ON DELETE CASCADE,
    creato_il  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_ticket_riserva_pannello ON ticket_riserva (panel_id);
