-- NF-24 (r12, #142): voce di Yokai. Scelte del server e testo dietro ogni vocale (per i bottoni «Trascrivi» e «Nella mia lingua»).
CREATE TABLE IF NOT EXISTS ai_voce_config (
    guild_id      BIGINT PRIMARY KEY,
    attiva        BOOLEAN NOT NULL DEFAULT FALSE,
    tono          TEXT NOT NULL DEFAULT 'scherzosa' CHECK (tono IN ('dolce', 'scherzosa', 'provocante', 'piccante')),
    canali_saluti BIGINT[] NOT NULL DEFAULT '{}',
    aggiornato_il TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ai_vocali (
    message_id BIGINT PRIMARY KEY,
    guild_id   BIGINT,
    channel_id BIGINT NOT NULL,
    testo      TEXT NOT NULL,
    lingua     TEXT NOT NULL DEFAULT 'it',
    creato_il  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ai_vocali_guild ON ai_vocali (guild_id);
CREATE INDEX IF NOT EXISTS ai_vocali_data ON ai_vocali (creato_il);
