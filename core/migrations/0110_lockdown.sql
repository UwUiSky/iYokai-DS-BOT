-- NF-29 (#100): blocco totale del server e modalita' panico.
-- lockdown_config: scelte del server (categorie escluse, ruoli da avvisare, sblocco automatico...).
-- lockdown_stato: un blocco al massimo per server, con quello che serve per riaprire
--   (livello di verifica di prima, inviti chiusi da noi, scadenza).
-- lockdown_canali: i permessi di @everyone PRIMA del blocco, un canale per riga.
--   La riga si scrive prima di toccare il canale: se il bot si ferma a meta', "togli" riapre comunque.
CREATE TABLE IF NOT EXISTS lockdown_config (
    guild_id            BIGINT PRIMARY KEY,
    categorie_escluse   BIGINT[]  NOT NULL DEFAULT '{}',
    ruoli_avviso        BIGINT[]  NOT NULL DEFAULT '{}',
    sblocco_auto_minuti INTEGER   NOT NULL DEFAULT 0,
    solo_proprietario   BOOLEAN   NOT NULL DEFAULT TRUE,
    automatico          BOOLEAN   NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS lockdown_stato (
    guild_id               BIGINT PRIMARY KEY,
    tipo                   TEXT        NOT NULL DEFAULT 'blocco',   -- blocco | panico
    stato                  TEXT        NOT NULL DEFAULT 'in_corso', -- in_corso | attivo | in_riapertura
    avviato_da             BIGINT      NOT NULL,
    avviato_il             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finisce_il             TIMESTAMPTZ,
    motivo                 TEXT        NOT NULL DEFAULT '',
    verifica_prima         TEXT,        -- livello di verifica da rimettere (NULL = non toccato)
    inviti_chiusi_da_noi   BOOLEAN     NOT NULL DEFAULT FALSE,
    solo_proprietario      BOOLEAN     NOT NULL DEFAULT FALSE
);
CREATE INDEX IF NOT EXISTS idx_lockdown_stato_finisce ON lockdown_stato (finisce_il) WHERE finisce_il IS NOT NULL;

CREATE TABLE IF NOT EXISTS lockdown_canali (
    guild_id      BIGINT  NOT NULL,
    channel_id    BIGINT  NOT NULL,
    prima         TEXT    NOT NULL,   -- JSON {permesso: true|false|null}
    ripristinato  BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (guild_id, channel_id)
);
