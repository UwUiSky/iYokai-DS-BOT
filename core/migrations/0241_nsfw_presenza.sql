-- NF-23 (#94), D6: presenza del SOLO bot NSFW (applicazione separata): i suoi dati si cancellano 90 giorni dopo la
-- sua uscita (D6), anche dove il bot principale non c'è mai stato; restano se esce solo il principale.
CREATE TABLE IF NOT EXISTS nsfw_presenza (
    guild_id  BIGINT PRIMARY KEY,
    uscito_il TIMESTAMPTZ
);
