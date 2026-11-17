-- Catalogo #123 (RUO-084): numero di membri di ogni ruolo mostrato nel menu.
ALTER TABLE role_menus ADD COLUMN IF NOT EXISTS show_counts BOOLEAN NOT NULL DEFAULT FALSE;
