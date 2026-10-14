-- NF-27 (#98): chi ha invitato chi. Una riga per membro (se rientra, la riga si aggiorna).
CREATE TABLE IF NOT EXISTS invite_joins (
    guild_id   BIGINT NOT NULL,
    user_id    BIGINT NOT NULL,
    inviter_id BIGINT NOT NULL,
    code       TEXT NOT NULL,
    joined_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    left_at    TIMESTAMPTZ,
    PRIMARY KEY (guild_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_invite_joins_inviter ON invite_joins (guild_id, inviter_id);
