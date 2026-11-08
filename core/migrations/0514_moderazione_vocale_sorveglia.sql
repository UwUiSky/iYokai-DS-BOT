-- Sorveglianza della voce (MOD-112): lo staff chiede di essere avvisato quando un utente entra in un vocale.
-- Dura 24 ore; la riga si cancella quando l'avviso parte.
CREATE TABLE IF NOT EXISTS moderation_vocale_sorveglia (
    guild_id   BIGINT      NOT NULL,
    user_id    BIGINT      NOT NULL,
    staff_id   BIGINT      NOT NULL,
    scade_at   TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (guild_id, user_id, staff_id)
);
CREATE INDEX IF NOT EXISTS idx_moderation_vocale_sorveglia_scade ON moderation_vocale_sorveglia (scade_at);
