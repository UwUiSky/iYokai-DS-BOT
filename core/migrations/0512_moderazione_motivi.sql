-- Motivi pronti di moderazione (MOD-113): al massimo 25 per server, nome fino a 32 caratteri, testo fino a 512.
CREATE TABLE IF NOT EXISTS moderation_motivi (
    id         BIGSERIAL   PRIMARY KEY,
    guild_id   BIGINT      NOT NULL,
    nome       TEXT        NOT NULL,
    testo      TEXT        NOT NULL,
    autore_id  BIGINT      NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_moderation_motivi_nome ON moderation_motivi (guild_id, lower(nome));
