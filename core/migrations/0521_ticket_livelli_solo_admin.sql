-- TKT-045: livello dei ruoli dello staff dei ticket. Senza riga il ruolo è «addetto» (vede e risponde);
-- «admin» chiude, forza la chiusura e usa «Solo admin».
CREATE TABLE IF NOT EXISTS ticket_ruoli_livello (
    guild_id BIGINT NOT NULL,
    role_id  BIGINT NOT NULL,
    livello  VARCHAR(10) NOT NULL CHECK (livello IN ('addetto', 'admin')),
    PRIMARY KEY (guild_id, role_id)
);
-- TKT-046: ticket visibile solo agli admin dei ticket (scelto per ticket o come base del pannello).
ALTER TABLE tickets ADD COLUMN IF NOT EXISTS solo_admin BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE ticket_panel_opzioni ADD COLUMN IF NOT EXISTS solo_admin BOOLEAN NOT NULL DEFAULT FALSE;
