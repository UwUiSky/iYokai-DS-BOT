-- Catalogo #128 (UTL-009, 012, 014, 018): nomi alternativi dei tag (alias, al massimo 3 per tag), pausa per utente,
-- canale o server, elenchi di ruoli, canali e utenti vietati (al massimo 10 per elenco), embed salvato collegato.
ALTER TABLE custom_commands
    ADD COLUMN IF NOT EXISTS pausa_ambito   TEXT NOT NULL DEFAULT 'utente',
    ADD COLUMN IF NOT EXISTS ruoli_vietati  BIGINT[] NOT NULL DEFAULT '{}',
    ADD COLUMN IF NOT EXISTS canali_vietati BIGINT[] NOT NULL DEFAULT '{}',
    ADD COLUMN IF NOT EXISTS utenti_vietati BIGINT[] NOT NULL DEFAULT '{}',
    ADD COLUMN IF NOT EXISTS embed_nome     TEXT;
ALTER TABLE custom_commands DROP CONSTRAINT IF EXISTS custom_commands_extra_check;
ALTER TABLE custom_commands ADD CONSTRAINT custom_commands_extra_check
    CHECK (pausa_ambito IN ('utente', 'canale', 'server')
       AND cardinality(ruoli_vietati) <= 10 AND cardinality(canali_vietati) <= 10 AND cardinality(utenti_vietati) <= 10
       AND (embed_nome IS NULL OR char_length(embed_nome) BETWEEN 1 AND 32));

CREATE TABLE IF NOT EXISTS tag_alias (
    guild_id BIGINT NOT NULL,
    alias    TEXT NOT NULL CHECK (char_length(alias) BETWEEN 1 AND 32),
    name     TEXT NOT NULL,
    PRIMARY KEY (guild_id, alias),
    FOREIGN KEY (guild_id, name) REFERENCES custom_commands (guild_id, name) ON DELETE CASCADE ON UPDATE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_tag_alias_nome ON tag_alias (guild_id, name);
