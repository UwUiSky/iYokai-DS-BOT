-- STA-034..052 (#130): contatori con parametro (ruolo, indirizzo di gioco, canale social),
-- traguardi successivi, orologio e testo fisso. Toglie il vincolo sui tipi della 0087, che bloccava
-- ticket, ruoli, canali ed emoji: i tipi validi li controlla core/counter_logic.py.
ALTER TABLE counters DROP CONSTRAINT IF EXISTS counters_kind_check;
ALTER TABLE counters
    ADD COLUMN IF NOT EXISTS param   TEXT CHECK (param IS NULL OR char_length(param) <= 200),
    ADD COLUMN IF NOT EXISTS targets TEXT CHECK (targets IS NULL OR char_length(targets) <= 200),
    ADD COLUMN IF NOT EXISTS last_name TEXT;
