-- NF-34 (#105): moduli e candidature. Fino a 5 domande per modulo, risposte con Accetta/Rifiuta.
CREATE TABLE IF NOT EXISTS forms (
    id              SERIAL PRIMARY KEY,
    guild_id        BIGINT NOT NULL,
    name            TEXT NOT NULL CHECK (char_length(name) BETWEEN 1 AND 32),
    title           TEXT NOT NULL CHECK (char_length(title) BETWEEN 1 AND 45),
    review_channel_id BIGINT NOT NULL,
    accept_role_id  BIGINT,
    questions       JSONB NOT NULL,
    created_by      BIGINT NOT NULL,
    UNIQUE (guild_id, name)
);

CREATE TABLE IF NOT EXISTS form_responses (
    id                SERIAL PRIMARY KEY,
    form_id           INTEGER NOT NULL REFERENCES forms(id) ON DELETE CASCADE,
    guild_id          BIGINT NOT NULL,
    user_id           BIGINT NOT NULL,
    answers           JSONB NOT NULL,
    status            TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'accepted', 'rejected')),
    review_message_id BIGINT,
    decided_by        BIGINT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- Una sola candidatura in attesa per persona e modulo.
CREATE UNIQUE INDEX IF NOT EXISTS uq_form_responses_pending
    ON form_responses (form_id, user_id) WHERE status = 'pending';
