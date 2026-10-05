-- LIM-18: nome della gilda, nome e descrizione degli oggetti dello shop
-- e premio dei giveaway ora hanno una lunghezza massima sui comandi.
-- I valori più lunghi salvati prima di quel limite vengono accorciati
-- qui una volta sola: un nome di gilda oltre i 256 caratteri rompeva
-- /clan info per sempre.
UPDATE clans SET name = left(name, 64) WHERE char_length(name) > 64;
UPDATE shop_items SET name = left(name, 80) WHERE char_length(name) > 80;
UPDATE shop_items SET description = left(description, 200) WHERE char_length(description) > 200;
UPDATE giveaways SET prize = left(prize, 200) WHERE char_length(prize) > 200;
