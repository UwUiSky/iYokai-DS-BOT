-- Blocco A, voce 1: ogni ban che un server prova a propagare lascia una riga (punteggio, esito):
-- serve al ritmo dei ban, alle conferme di altri server e a spiegare il perché allo staff.
-- Le proposte della rete dei ban portano il punteggio e i codici che l'hanno deciso.
CREATE TABLE IF NOT EXISTS global_ban_episodi (
    id               BIGSERIAL PRIMARY KEY,
    source_guild_id  BIGINT NOT NULL,
    user_id          BIGINT NOT NULL,
    punteggio        SMALLINT NOT NULL,
    codici           TEXT NOT NULL DEFAULT '',
    esito            TEXT NOT NULL,
    creato_il        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_gb_episodi_sorgente ON global_ban_episodi (source_guild_id, creato_il DESC);
CREATE INDEX IF NOT EXISTS idx_gb_episodi_utente ON global_ban_episodi (user_id, creato_il DESC);

ALTER TABLE rete_ban_proposte ADD COLUMN IF NOT EXISTS punteggio SMALLINT;
ALTER TABLE rete_ban_proposte ADD COLUMN IF NOT EXISTS codici TEXT;
