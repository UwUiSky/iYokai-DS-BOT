-- NF-28: un giveaway programmato che non riesce a partire (canale sparito, bot
-- senza permessi) non si chiude come finito: resta in elenco con il motivo, e
-- lo staff può annullarlo.
ALTER TABLE giveaways
    ADD COLUMN IF NOT EXISTS errore TEXT;
