-- D127 (#115): shadowban. I ruoli tolti si salvano PRIMA di toccare il membro; la chiave unica fa vincere un solo shadowban per persona.
CREATE TABLE IF NOT EXISTS moderation_shadowban (
    guild_id     BIGINT NOT NULL,
    user_id      BIGINT NOT NULL,
    ruoli        BIGINT[] NOT NULL DEFAULT '{}',
    case_number  INTEGER,
    finisce_il   TIMESTAMPTZ,
    dato_da      BIGINT,
    PRIMARY KEY (guild_id, user_id)
);

-- Il ruolo e i due canali dedicati di ogni server (creati dal bot o scelti dallo staff).
CREATE TABLE IF NOT EXISTS moderation_shadowban_config (
    guild_id          BIGINT PRIMARY KEY,
    ruolo_id          BIGINT,
    canale_testo_id   BIGINT,
    canale_vocale_id  BIGINT
);
