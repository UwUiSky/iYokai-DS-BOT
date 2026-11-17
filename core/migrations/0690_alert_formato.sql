-- #129 (ALR-009, 014, 024): Short di YouTube (tutti/no/solo), formato dell'avviso (testo/embed)
-- ed embed salvato da usare come modello.
ALTER TABLE alert_options ADD COLUMN IF NOT EXISTS shorts     TEXT NOT NULL DEFAULT 'tutti';
ALTER TABLE alert_options ADD COLUMN IF NOT EXISTS formato    TEXT NOT NULL DEFAULT 'testo';
ALTER TABLE alert_options ADD COLUMN IF NOT EXISTS embed_nome TEXT NOT NULL DEFAULT '';
