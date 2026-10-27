-- RUO-016 (#123): messaggio pubblico quando un membro viene bannato (vuoto = spento; va nel canale dell'addio).
ALTER TABLE greetings_config ADD COLUMN IF NOT EXISTS ban_message TEXT NOT NULL DEFAULT '';
