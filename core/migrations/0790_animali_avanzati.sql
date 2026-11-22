-- #125 r6eco (ECO-125..129): pet sitter, lotte, incontri con cuccioli, adozioni. Gli animali senza padrone hanno user_id = 0.
ALTER TABLE economia_animali ADD COLUMN IF NOT EXISTS sitter_fino TIMESTAMPTZ;
ALTER TABLE economia_animali ADD COLUMN IF NOT EXISTS lotta_at TIMESTAMPTZ;
ALTER TABLE economia_animali ADD COLUMN IF NOT EXISTS ex_proprietario BIGINT;

-- Un incontro per coppia di animali al giorno (a < b).
CREATE TABLE IF NOT EXISTS economia_animali_incontri (
    guild_id BIGINT NOT NULL,
    giorno   DATE   NOT NULL,
    a_id     BIGINT NOT NULL,
    b_id     BIGINT NOT NULL,
    PRIMARY KEY (guild_id, giorno, a_id, b_id),
    CHECK (a_id < b_id)
);
