-- NF-40: attesa tra due partite di /fun gioca decisa dal database, non da una
-- cache in memoria: due richieste insieme non passano entrambe.
ALTER TABLE leveling_totals
    ADD COLUMN IF NOT EXISTS ultima_partita_at TIMESTAMPTZ;
