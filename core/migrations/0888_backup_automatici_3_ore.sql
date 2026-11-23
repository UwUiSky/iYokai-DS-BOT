-- SIC-016 (D121): la copia automatica può farsi ogni 3 ore (prima 4).
ALTER TABLE backup_automatici DROP CONSTRAINT IF EXISTS backup_automatici_ore_check;
ALTER TABLE backup_automatici ADD CONSTRAINT backup_automatici_ore_check CHECK (ore BETWEEN 3 AND 168);
