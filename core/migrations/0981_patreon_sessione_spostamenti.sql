-- Blocco A, voce 4 (Patreon): lo stato OAuth è legato alla sessione del pannello che ha cominciato il collegamento;
-- un Patreon già collegato a un'altra persona si sposta solo dopo una conferma esplicita (qui restano i token in attesa,
-- cifrati, per 10 minuti); gli eventi del webhook più vecchi dell'ultimo addebito già visto si ignorano.
ALTER TABLE patreon_stati ADD COLUMN IF NOT EXISTS sessione_impronta TEXT;
-- Gli stati già emessi non hanno sessione: non valgono più (durano 10 minuti).
DELETE FROM patreon_stati WHERE sessione_impronta IS NULL;

CREATE TABLE IF NOT EXISTS patreon_spostamenti (
    discord_user_id BIGINT PRIMARY KEY,
    patreon_id      TEXT NOT NULL,
    token_cifrato   TEXT NOT NULL,
    refresh_cifrato TEXT,
    attivo          BOOLEAN NOT NULL DEFAULT FALSE,
    tiers           TEXT[] NOT NULL DEFAULT '{}',
    scade_il        TIMESTAMPTZ NOT NULL
);

ALTER TABLE patreon_membri ADD COLUMN IF NOT EXISTS ultima_carica TIMESTAMPTZ;
