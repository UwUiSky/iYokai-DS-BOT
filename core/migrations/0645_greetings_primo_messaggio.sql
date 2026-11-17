-- Catalogo #123 (RUO-024): emoji messa dal bot sul primo messaggio di un nuovo membro ('' = spenta).
ALTER TABLE greetings_config ADD COLUMN IF NOT EXISTS first_message_reaction TEXT NOT NULL DEFAULT '';
