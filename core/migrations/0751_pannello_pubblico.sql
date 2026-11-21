-- STA-012, LIV-062, STA-061 (#130, #124): cosa un server rende pubblico dal pannello web.
--  - statistiche pubbliche (e, a parte, la lista dei membri);
--  - indirizzo breve della classifica (unico in tutto il bot, senza maiuscole);
--  - chiave per l'API di sola lettura: si salva solo l'impronta SHA-256 e le prime lettere, mai la chiave.
CREATE TABLE IF NOT EXISTS web_panel_pubblico (
    guild_id        BIGINT      PRIMARY KEY,
    stat_pubbliche  BOOLEAN     NOT NULL DEFAULT FALSE,
    stat_membri     BOOLEAN     NOT NULL DEFAULT FALSE,
    classifica_slug TEXT        CHECK (classifica_slug IS NULL OR classifica_slug ~ '^[a-z0-9]([a-z0-9-]{1,30})[a-z0-9]$'),
    api_impronta    TEXT        CHECK (api_impronta IS NULL OR char_length(api_impronta) = 64),
    api_prefisso    TEXT        CHECK (api_prefisso IS NULL OR char_length(api_prefisso) <= 12),
    api_creata_il   TIMESTAMPTZ,
    api_creata_da   BIGINT,
    aggiornato_il   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS web_panel_pubblico_slug ON web_panel_pubblico (classifica_slug) WHERE classifica_slug IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS web_panel_pubblico_chiave ON web_panel_pubblico (api_impronta) WHERE api_impronta IS NOT NULL;
