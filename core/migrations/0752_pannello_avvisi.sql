-- CFG-006 (#122): avvisi del pannello web. Ognuno sceglie, per categoria e per server, se riceverli nel sito o in DM
-- (spento = nessun avviso). Niente email: nessun servizio di posta è configurato.
-- Gli avvisi nel sito si tengono 30 giorni e al massimo 50 per persona e per server.
CREATE TABLE IF NOT EXISTS web_panel_avvisi_pref (
    guild_id  BIGINT NOT NULL,
    user_id   BIGINT NOT NULL,
    categoria TEXT   NOT NULL CHECK (char_length(categoria) BETWEEN 1 AND 30),
    canale    TEXT   NOT NULL CHECK (canale IN ('sito', 'dm')),
    PRIMARY KEY (guild_id, user_id, categoria)
);
CREATE INDEX IF NOT EXISTS web_panel_avvisi_pref_categoria ON web_panel_avvisi_pref (guild_id, categoria);
CREATE TABLE IF NOT EXISTS web_panel_avvisi (
    id        BIGSERIAL   PRIMARY KEY,
    guild_id  BIGINT      NOT NULL,
    user_id   BIGINT      NOT NULL,
    categoria TEXT        NOT NULL CHECK (char_length(categoria) BETWEEN 1 AND 30),
    testo     TEXT        NOT NULL CHECK (char_length(testo) <= 300),
    creato_il TIMESTAMPTZ NOT NULL DEFAULT now(),
    letto     BOOLEAN     NOT NULL DEFAULT FALSE
);
CREATE INDEX IF NOT EXISTS web_panel_avvisi_utente ON web_panel_avvisi (guild_id, user_id, id DESC);
