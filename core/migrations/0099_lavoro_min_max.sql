-- NF-15: il minimo del comando di lavoro non supera mai il massimo, deciso dal
-- database (due modifiche insieme non possono rompere l'ordine).
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'leveling_settings_work_ordine'
    ) THEN
        ALTER TABLE leveling_settings
            ADD CONSTRAINT leveling_settings_work_ordine CHECK (work_min <= work_max) NOT VALID;
    END IF;
END $$;
