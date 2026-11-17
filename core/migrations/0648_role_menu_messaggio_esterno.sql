-- Catalogo #123 (RUO-072, 073): menu a reazioni agganciato a un messaggio scritto da altri
-- (il bot non lo modifica né lo cancella: mette solo le sue reazioni).
ALTER TABLE role_menus ADD COLUMN IF NOT EXISTS external BOOLEAN NOT NULL DEFAULT FALSE;
