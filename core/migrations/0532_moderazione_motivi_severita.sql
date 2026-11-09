-- D68: i motivi pronti hanno severità, sanzione e durata di base; un segno per server dice che l'elenco di base è già stato dato.
ALTER TABLE moderation_motivi ADD COLUMN IF NOT EXISTS severita TEXT;
ALTER TABLE moderation_motivi ADD COLUMN IF NOT EXISTS azione   TEXT;
ALTER TABLE moderation_motivi ADD COLUMN IF NOT EXISTS durata_s INTEGER;
CREATE TABLE IF NOT EXISTS moderation_motivi_semina (
    guild_id   BIGINT      PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
