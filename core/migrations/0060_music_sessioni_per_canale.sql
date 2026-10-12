-- M 8.6 (#64): un bot musicale per canale vocale, non per server.
-- La sessione ora si distingue per (server, canale): due canali vocali nello stesso
-- server hanno due bot e due code. Le righe vecchie valgono solo per la vita del
-- processo (main() le svuota all'avvio), quindi il canale 0 dei vecchi dati non conta.
ALTER TABLE music_sessions ADD COLUMN IF NOT EXISTS channel_id BIGINT NOT NULL DEFAULT 0;
ALTER TABLE music_sessions DROP CONSTRAINT IF EXISTS music_sessions_pkey;
ALTER TABLE music_sessions ADD PRIMARY KEY (guild_id, channel_id);
