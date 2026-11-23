-- ECO-051 (D121): sondaggio con un premio in monete estratto tra chi ha votato.
ALTER TABLE sondaggi_nativi ADD COLUMN IF NOT EXISTS premio INTEGER CHECK (premio IS NULL OR premio BETWEEN 1 AND 100000);
ALTER TABLE sondaggi_nativi ADD COLUMN IF NOT EXISTS vincitori SMALLINT NOT NULL DEFAULT 1 CHECK (vincitori BETWEEN 1 AND 10);
ALTER TABLE sondaggi_nativi ADD COLUMN IF NOT EXISTS premiato BOOLEAN NOT NULL DEFAULT FALSE;
