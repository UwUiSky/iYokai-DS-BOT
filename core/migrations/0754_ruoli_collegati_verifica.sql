-- VER-027 (#121): verifica con i ruoli collegati di Discord. Una riga per persona che ha collegato la verifica dal sito.
-- Il token di Discord sta SOLO cifrato (AES-256-GCM, core/oauth_crypto). Nessun altro dato: l'età dell'account si ricava dall'ID.
CREATE TABLE IF NOT EXISTS ruoli_collegati_verifica (
    user_id          BIGINT      PRIMARY KEY,
    discord_token    TEXT        NOT NULL,
    discord_refresh  TEXT,
    discord_scade_il TIMESTAMPTZ,
    verificato       BOOLEAN     NOT NULL DEFAULT FALSE,
    avatar_presente  BOOLEAN     NOT NULL DEFAULT FALSE,
    collegato_il     TIMESTAMPTZ NOT NULL DEFAULT now(),
    aggiornato_il    TIMESTAMPTZ NOT NULL DEFAULT now()
);
