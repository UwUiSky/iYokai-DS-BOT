-- Catalogo #123 (RUO-087): voce «togli tutti i ruoli» in fondo alla tendina.
ALTER TABLE role_menus ADD COLUMN IF NOT EXISTS reset_option BOOLEAN NOT NULL DEFAULT FALSE;
