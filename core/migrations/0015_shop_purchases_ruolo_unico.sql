-- BUG-14 (#23): un oggetto dello shop che dà un ruolo si compra una
-- volta sola per utente. Il controllo ora lo fa il database, con un
-- indice unico sugli acquisti "a ruolo". Gli oggetti senza ruolo
-- restano acquistabili più volte (role_id resta NULL).
ALTER TABLE shop_purchases ADD COLUMN IF NOT EXISTS role_id BIGINT;

-- Acquisti già registrati: prendono il ruolo dal loro oggetto.
UPDATE shop_purchases p
SET role_id = i.role_id
FROM shop_items i
WHERE i.id = p.item_id
  AND i.guild_id = p.guild_id
  AND i.role_id IS NOT NULL
  AND p.role_id IS NULL;

-- Doppioni nati prima del vincolo: resta l'acquisto più vecchio.
DELETE FROM shop_purchases p
USING shop_purchases q
WHERE p.role_id IS NOT NULL
  AND q.role_id IS NOT NULL
  AND p.guild_id = q.guild_id
  AND p.user_id = q.user_id
  AND p.item_id = q.item_id
  AND p.id > q.id;

CREATE UNIQUE INDEX IF NOT EXISTS uq_shop_purchases_ruolo
    ON shop_purchases (guild_id, user_id, item_id)
    WHERE role_id IS NOT NULL;
