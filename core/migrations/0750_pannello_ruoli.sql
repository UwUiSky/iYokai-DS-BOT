-- CFG-002 (#122): chi può usare il pannello web oltre a chi ha «Gestisci server» o il ruolo admin del bot.
-- Due livelli per ruolo: «lettura» (vede le pagine) e «scrittura» (salva). Un ruolo ha un solo livello.
-- I tetti (10 ruoli per livello) stanno nel codice, sotto un blocco per server.
CREATE TABLE IF NOT EXISTS web_panel_ruoli (
    guild_id    BIGINT      NOT NULL,
    role_id     BIGINT      NOT NULL,
    livello     TEXT        NOT NULL CHECK (livello IN ('lettura', 'scrittura')),
    impostato_da BIGINT,
    impostato_il TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (guild_id, role_id)
);
