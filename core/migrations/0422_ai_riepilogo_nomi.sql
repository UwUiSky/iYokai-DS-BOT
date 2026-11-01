-- NF-24 (r12): riepilogo del server a orario, avvisi su parole chiave, nomi a tema per punti e titoli.
ALTER TABLE ai_config ADD COLUMN IF NOT EXISTS nome_punti      TEXT CHECK (nome_punti IS NULL OR char_length(nome_punti) <= 20);
ALTER TABLE ai_config ADD COLUMN IF NOT EXISTS prefisso_titolo TEXT CHECK (prefisso_titolo IS NULL OR char_length(prefisso_titolo) <= 20);

CREATE TABLE IF NOT EXISTS ai_riepiloghi (
    guild_id      BIGINT PRIMARY KEY,
    attivo        BOOLEAN NOT NULL DEFAULT FALSE,
    canale_id     BIGINT,
    ora           SMALLINT NOT NULL DEFAULT 9 CHECK (ora BETWEEN 0 AND 23),
    frequenza     TEXT NOT NULL DEFAULT 'giorno' CHECK (frequenza IN ('giorno', 'settimana')),
    con_testo     BOOLEAN NOT NULL DEFAULT FALSE,
    canali_testo  BIGINT[] NOT NULL DEFAULT '{}',
    ultimo_invio  TIMESTAMPTZ,
    aggiornato_il TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ai_avvisi_parole (
    guild_id BIGINT NOT NULL,
    user_id  BIGINT NOT NULL,
    parola   TEXT NOT NULL CHECK (char_length(parola) BETWEEN 2 AND 30),
    creato_il TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (guild_id, user_id, parola)
);
CREATE INDEX IF NOT EXISTS ai_avvisi_parole_guild ON ai_avvisi_parole (guild_id);
