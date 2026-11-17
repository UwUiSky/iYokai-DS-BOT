-- #126 (r4mus): MUS-011 fonti accese o spente dall'owner a bot acceso; MUS-063 parole vietate in tutto il bot.
CREATE TABLE IF NOT EXISTS music_sources_override (
    source      TEXT PRIMARY KEY CHECK (char_length(source) BETWEEN 1 AND 30),
    enabled     BOOLEAN NOT NULL,
    changed_by  BIGINT NOT NULL,
    changed_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS music_global_banned_words (
    word        TEXT PRIMARY KEY CHECK (char_length(word) BETWEEN 2 AND 60),
    added_by    BIGINT NOT NULL,
    added_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
