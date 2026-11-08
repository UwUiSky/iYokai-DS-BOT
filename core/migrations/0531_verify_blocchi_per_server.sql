-- D67: un blocco per persona e per server (prima uno solo per persona: valeva l'ultimo). Chi è limitato in più
-- server (account rubato) apre il ticket ModMail con lo staff di ciascuno. La chiave inizia da user_id: serve
-- già alla ricerca per persona del ModMail.
ALTER TABLE verify_blocchi DROP CONSTRAINT IF EXISTS verify_blocchi_pkey;
ALTER TABLE verify_blocchi ADD CONSTRAINT verify_blocchi_pkey PRIMARY KEY (user_id, guild_id);
