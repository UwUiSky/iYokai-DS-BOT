-- D67: storico condiviso più severo e IP cifrati solo per il proprietario del bot.
-- `founder_id` (owner del server) e `admin_id` (chi ha premuto «Lascia passare») servono alla soglia di 3
-- approvazioni diverse. Le righe di prima li hanno vuoti e non contano per gli altri server.
ALTER TABLE verify_vpn_storico ADD COLUMN IF NOT EXISTS founder_id BIGINT;
ALTER TABLE verify_vpn_storico ADD COLUMN IF NOT EXISTS admin_id BIGINT;
-- `verify_ip`: l'IP di ogni verifica web, CIFRATO (AES-256-GCM, chiave VERIFY_IP_ENCRYPTION_KEY, legato a
-- server e persona). Lo legge solo il proprietario del bot. `ip_impronta` (HMAC) evita righe doppie.
-- `motivo` dice perché c'è una scadenza: uscita, server (bot tolto), kick, ban, sblocco. Con motivo `ban`
-- la scadenza è vuota finché il ban è attivo; dopo lo sblocco sono 30 giorni.
CREATE TABLE IF NOT EXISTS verify_ip (
    id          BIGSERIAL PRIMARY KEY,
    guild_id    BIGINT NOT NULL,
    user_id     BIGINT NOT NULL,
    ip_impronta TEXT NOT NULL,
    ip_cifrato  TEXT NOT NULL,
    esito       TEXT NOT NULL DEFAULT 'passato' CHECK (esito IN ('passato', 'bloccato', 'da_storico', 'eccezione')),
    creato_il   TIMESTAMPTZ NOT NULL DEFAULT now(),
    ultimo_il   TIMESTAMPTZ NOT NULL DEFAULT now(),
    motivo      TEXT CHECK (motivo IN ('uscita', 'server', 'kick', 'ban', 'sblocco')),
    scade_il    TIMESTAMPTZ,
    UNIQUE (guild_id, user_id, ip_impronta)
);
CREATE INDEX IF NOT EXISTS idx_verify_ip_utente ON verify_ip (user_id);
CREATE INDEX IF NOT EXISTS idx_verify_ip_server ON verify_ip (guild_id);
