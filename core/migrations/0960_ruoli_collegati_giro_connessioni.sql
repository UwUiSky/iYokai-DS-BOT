-- ALR-049 (#129, D127): giro periodico dei ruoli collegati Twitch e invito dalle connessioni del profilo Discord.
-- `aggiornato_il`: ultimo giro riuscito; `errori`: giri di fila andati male per un errore passeggero.
ALTER TABLE ruoli_collegati_twitch ADD COLUMN IF NOT EXISTS aggiornato_il TIMESTAMPTZ;
ALTER TABLE ruoli_collegati_twitch ADD COLUMN IF NOT EXISTS errori SMALLINT NOT NULL DEFAULT 0;
-- Solo due sì/no per persona (ha Twitch, ha Kick collegato al profilo Discord). Nessun nome, nessun ID, nessun token:
-- il token della lettura delle connessioni si revoca subito. Si scrive solo con il consenso OAuth `connections`.
CREATE TABLE IF NOT EXISTS ruoli_collegati_connessioni (
    user_id        BIGINT      PRIMARY KEY,
    ha_twitch      BOOLEAN     NOT NULL DEFAULT FALSE,
    ha_kick        BOOLEAN     NOT NULL DEFAULT FALSE,
    controllato_il TIMESTAMPTZ NOT NULL DEFAULT now()
);
