-- STA-025..028, 013, 032, 006, 008 (#130): filtri delle statistiche, accesso, anonimato,
-- stato della voce, regole con due condizioni e campioni dei membri online.
-- Solo numeri: mai il testo di un messaggio.
ALTER TABLE activity_settings
    ADD COLUMN IF NOT EXISTS channel_mode    TEXT NOT NULL DEFAULT 'escludi' CHECK (channel_mode IN ('escludi', 'solo')),
    ADD COLUMN IF NOT EXISTS role_mode       TEXT NOT NULL DEFAULT 'escludi' CHECK (role_mode IN ('escludi', 'solo')),
    ADD COLUMN IF NOT EXISTS ignored_members BIGINT[] NOT NULL DEFAULT '{}',
    ADD COLUMN IF NOT EXISTS view_roles      BIGINT[] NOT NULL DEFAULT '{}',
    ADD COLUMN IF NOT EXISTS track_online    BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE activity_roles
    ADD COLUMN IF NOT EXISTS metric2    TEXT CHECK (metric2 IS NULL OR metric2 IN ('messages', 'voice_minutes')),
    ADD COLUMN IF NOT EXISTS threshold2 INTEGER CHECK (threshold2 IS NULL OR threshold2 > 0),
    ADD COLUMN IF NOT EXISTS combine    TEXT NOT NULL DEFAULT 'e' CHECK (combine IN ('e', 'o'));

-- Secondi in vocale divisi per stato (STA-006): un sottoinsieme dei secondi di activity_member_daily,
-- più i secondi nel canale AFK (che non contano come vocale).
CREATE TABLE IF NOT EXISTS activity_voice_state_daily (
    guild_id      BIGINT NOT NULL,
    day           DATE   NOT NULL,
    user_id       BIGINT NOT NULL,
    muted_seconds INTEGER NOT NULL DEFAULT 0,
    deaf_seconds  INTEGER NOT NULL DEFAULT 0,
    afk_seconds   INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (guild_id, day, user_id)
);

-- Chi vuole comparire come «utente anonimo» nelle classifiche (STA-028). Vale per tutti i server e per il passato.
CREATE TABLE IF NOT EXISTS activity_anonymous (
    user_id    BIGINT PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Membri online stimati, un campione all'ora (STA-008). Solo dove l'admin lo accende.
CREATE TABLE IF NOT EXISTS activity_online_sample (
    guild_id BIGINT NOT NULL,
    ts       TIMESTAMPTZ NOT NULL,
    online   INTEGER NOT NULL,
    PRIMARY KEY (guild_id, ts)
);
