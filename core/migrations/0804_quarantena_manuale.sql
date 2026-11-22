-- Catalogo #115 (MOD-016): quarantena a mano. I ruoli tolti si salvano PRIMA di toccare il membro, per ridarli al rilascio.
CREATE TABLE IF NOT EXISTS moderation_quarantena (
    guild_id     BIGINT NOT NULL,
    user_id      BIGINT NOT NULL,
    ruoli        BIGINT[] NOT NULL DEFAULT '{}',
    case_number  INTEGER,
    finisce_il   TIMESTAMPTZ,
    dato_da      BIGINT,
    PRIMARY KEY (guild_id, user_id)
);
