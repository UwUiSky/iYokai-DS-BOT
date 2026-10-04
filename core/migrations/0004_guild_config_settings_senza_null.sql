-- BUG-31: il vecchio /config rollback metteva a `null` le chiavi di
-- settings invece di toglierle, e i cog che le leggono (ticket, log)
-- andavano in crash. jsonb_strip_nulls toglie le chiavi con valore null
-- (gli elementi null dentro una lista restano).
UPDATE guild_config
SET settings = jsonb_strip_nulls(settings)
WHERE settings <> jsonb_strip_nulls(settings);
