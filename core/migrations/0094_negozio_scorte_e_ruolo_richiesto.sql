-- ECO-062 e ECO-061 (#125): scorte limitate e ruolo richiesto per comprare.
-- Senza valori l'oggetto resta come prima (scorte illimitate, nessun ruolo richiesto).
ALTER TABLE shop_items
    ADD COLUMN IF NOT EXISTS stock             INT CHECK (stock IS NULL OR stock >= 0),
    ADD COLUMN IF NOT EXISTS required_role_id  BIGINT;
