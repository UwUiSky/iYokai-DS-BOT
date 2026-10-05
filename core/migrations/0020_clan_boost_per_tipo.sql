-- D23 (#146): boost del clan per tipo. Ogni beneficio (exp e coin) ha la
-- sua scadenza, sia per il membro (boost individuale) sia per la gilda.
-- Il boost che esiste oggi, ×2 a tutto, diventa un "super" già attivo:
-- la scadenza attuale si copia in entrambe le colonne nuove.
-- Le colonne vecchie (boost_expires_at, guild_boost_expires_at) restano
-- dove sono ma il codice non le usa più.
ALTER TABLE clan_members ADD COLUMN IF NOT EXISTS boost_exp_expires_at TIMESTAMPTZ;
ALTER TABLE clan_members ADD COLUMN IF NOT EXISTS boost_coin_expires_at TIMESTAMPTZ;
ALTER TABLE clans ADD COLUMN IF NOT EXISTS guild_boost_exp_expires_at TIMESTAMPTZ;
ALTER TABLE clans ADD COLUMN IF NOT EXISTS guild_boost_coin_expires_at TIMESTAMPTZ;

UPDATE clan_members
SET boost_exp_expires_at = boost_expires_at,
    boost_coin_expires_at = boost_expires_at
WHERE boost_expires_at IS NOT NULL;

UPDATE clans
SET guild_boost_exp_expires_at = guild_boost_expires_at,
    guild_boost_coin_expires_at = guild_boost_expires_at
WHERE guild_boost_expires_at IS NOT NULL;
