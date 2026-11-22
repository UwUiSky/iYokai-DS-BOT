-- TKT-086 (#120): il riassunto AI della conversazione di un ticket nel log, per pannello. Spento di base:
-- l'admin deve accenderlo (il testo del ticket va al fornitore AI, con le regole e i tetti dell'AI del server).
ALTER TABLE ai_ticket_pannelli ADD COLUMN IF NOT EXISTS riassunto_chiusura BOOLEAN NOT NULL DEFAULT FALSE;
