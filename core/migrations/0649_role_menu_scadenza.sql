-- Catalogo #123 (RUO-070): menu che si cancella da solo dopo un tempo.
ALTER TABLE role_menus ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ;
