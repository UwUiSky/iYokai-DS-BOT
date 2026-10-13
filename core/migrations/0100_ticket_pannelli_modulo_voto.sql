-- NF-13 (#84): pannelli di ticket multipli, modulo di domande, chiusura
-- automatica per inattività, voto alla chiusura.

CREATE TABLE IF NOT EXISTS ticket_panels (
    id                SERIAL PRIMARY KEY,
    guild_id          BIGINT NOT NULL,
    name              TEXT NOT NULL,
    category_id       BIGINT NOT NULL,
    button_label      TEXT NOT NULL,
    button_emoji      TEXT,
    welcome_text      TEXT,
    autoclose_minutes INTEGER CHECK (autoclose_minutes IS NULL OR autoclose_minutes BETWEEN 5 AND 43200),
    rating_enabled    BOOLEAN NOT NULL DEFAULT FALSE,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_ticket_panels_nome ON ticket_panels (guild_id, lower(name));

CREATE TABLE IF NOT EXISTS ticket_form_questions (
    id          SERIAL PRIMARY KEY,
    panel_id    INTEGER NOT NULL REFERENCES ticket_panels(id) ON DELETE CASCADE,
    position    SMALLINT NOT NULL CHECK (position BETWEEN 1 AND 5),
    label       TEXT NOT NULL,
    placeholder TEXT,
    required    BOOLEAN NOT NULL DEFAULT TRUE,
    long_answer BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE (panel_id, position) DEFERRABLE INITIALLY DEFERRED
);

ALTER TABLE tickets ADD COLUMN IF NOT EXISTS panel_id INTEGER;
ALTER TABLE tickets ADD COLUMN IF NOT EXISTS last_activity_at TIMESTAMPTZ;
ALTER TABLE tickets ADD COLUMN IF NOT EXISTS rating SMALLINT
    CHECK (rating IS NULL OR rating BETWEEN 1 AND 5);
ALTER TABLE tickets ADD COLUMN IF NOT EXISTS rated_at TIMESTAMPTZ;
