-- ECO-063, 065, 066, 067, 068 (#125): ordine e categorie degli oggetti dello shop,
-- testo di risposta dopo l'acquisto, ruolo comprato che scade, oggetti «a elenco».
-- Senza valori l'oggetto resta come prima.
ALTER TABLE shop_items
    ADD COLUMN IF NOT EXISTS sort_order          INT NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS category            TEXT,
    ADD COLUMN IF NOT EXISTS reply_text          TEXT,
    ADD COLUMN IF NOT EXISTS role_duration_hours INT CHECK (role_duration_hours IS NULL OR role_duration_hours > 0),
    ADD COLUMN IF NOT EXISTS list_item           BOOLEAN NOT NULL DEFAULT false;

-- Ruolo a tempo: quando scade, il lavoro periodico toglie il ruolo e mette role_id a NULL
-- (così l'acquisto resta nello storico e l'indice unico dei ruoli lascia ricomprare).
ALTER TABLE shop_purchases
    ADD COLUMN IF NOT EXISTS role_expires_at  TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS expiry_attempts  INT NOT NULL DEFAULT 0;
CREATE INDEX IF NOT EXISTS shop_purchases_scadenza
    ON shop_purchases (role_expires_at)
    WHERE role_expires_at IS NOT NULL AND role_id IS NOT NULL;

-- Oggetto «a elenco»: ogni acquisto consegna una riga diversa (codici, chiavi).
CREATE TABLE IF NOT EXISTS shop_item_lines (
    id           BIGSERIAL PRIMARY KEY,
    guild_id     BIGINT NOT NULL,
    item_id      INT NOT NULL,
    line         TEXT NOT NULL,
    buyer_id     BIGINT,
    purchase_id  INT,
    delivered_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS shop_item_lines_libere
    ON shop_item_lines (item_id, id) WHERE delivered_at IS NULL;
