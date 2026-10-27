-- Link d'invito personali «finto vanity» (r10): uno per membro e per server, passa dal sito.
-- Lo slug è unico in tutto il bot (l'indirizzo non contiene l'ID del server) e non cambia mai:
-- se il membro cambia nome, il vecchio indirizzo continua a funzionare.
CREATE TABLE IF NOT EXISTS invite_personal_links (
    slug         TEXT PRIMARY KEY,
    guild_id     BIGINT NOT NULL,
    user_id      BIGINT NOT NULL,
    discord_code TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_used_at TIMESTAMPTZ,
    UNIQUE (guild_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_invite_personal_links_code ON invite_personal_links (guild_id, discord_code);

-- Lo storico registra anche gli ingressi senza invitante noto e il tipo di link usato:
-- personale (dal sito), normale, vanity, sconosciuto.
ALTER TABLE invite_joins ALTER COLUMN inviter_id DROP NOT NULL;
ALTER TABLE invite_joins ALTER COLUMN code DROP NOT NULL;
ALTER TABLE invite_joins ADD COLUMN IF NOT EXISTS kind TEXT NOT NULL DEFAULT 'normale';
