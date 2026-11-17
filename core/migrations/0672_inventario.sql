-- #125 B3 (ECO-058, 059, 070, 071, 072, 086): inventario degli oggetti comprati nel negozio.
CREATE TABLE IF NOT EXISTS economia_inventario (
    guild_id BIGINT  NOT NULL,
    user_id  BIGINT  NOT NULL,
    item_id  INTEGER NOT NULL,
    quantita INTEGER NOT NULL CHECK (quantita >= 0),
    PRIMARY KEY (guild_id, user_id, item_id)
);
ALTER TABLE shop_items ADD COLUMN IF NOT EXISTS regalabile BOOLEAN NOT NULL DEFAULT TRUE;
