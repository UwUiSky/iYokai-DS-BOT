-- LOG-022 e LOG-024 (#119): il log dei messaggi può ignorare anche chi ha certi ruoli
-- e i messaggi che corrispondono a un'espressione regolare.
ALTER TABLE log_ignora DROP CONSTRAINT IF EXISTS log_ignora_genere_check;
ALTER TABLE log_ignora ADD CONSTRAINT log_ignora_genere_check
    CHECK (genere IN ('canale', 'utente', 'prefisso', 'ruolo', 'regex'));
