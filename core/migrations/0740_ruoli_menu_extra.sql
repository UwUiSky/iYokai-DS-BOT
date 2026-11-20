-- Catalogo #123 (RUO-083, 069, 046, 053): più ruoli per opzione, gruppo di menu, ruoli colore, immagine nel menu.
CREATE TABLE IF NOT EXISTS role_menu_option_roles (
    menu_id       INTEGER NOT NULL REFERENCES role_menus(id) ON DELETE CASCADE,
    role_id       BIGINT  NOT NULL,
    extra_role_id BIGINT  NOT NULL,
    PRIMARY KEY (menu_id, role_id, extra_role_id)
);
ALTER TABLE role_menus ADD COLUMN IF NOT EXISTS gruppo TEXT;
CREATE INDEX IF NOT EXISTS idx_role_menus_gruppo ON role_menus (guild_id, gruppo) WHERE gruppo IS NOT NULL;
ALTER TABLE role_menus ADD COLUMN IF NOT EXISTS colori BOOLEAN NOT NULL DEFAULT FALSE;
CREATE TABLE IF NOT EXISTS role_menu_images (
    menu_id    INTEGER PRIMARY KEY REFERENCES role_menus(id) ON DELETE CASCADE,
    image      BYTEA NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
