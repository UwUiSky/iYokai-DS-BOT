-- D65: blocchi della verifica e storico condiviso dei falsi positivi.
-- `verify_blocchi`: l'ultimo blocco di ogni persona (server e motivo, mai l'IP), per aprire il ticket
-- ModMail con il motivo quando la persona scrive in privato al bot. Scade in un giorno.
CREATE TABLE IF NOT EXISTS verify_blocchi (
    user_id   BIGINT PRIMARY KEY,
    guild_id  BIGINT NOT NULL,
    motivo    TEXT NOT NULL,
    creato_il TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- `verify_vpn_storico`: quando lo staff di un server lascia passare una persona segnalata come VPN/proxy.
-- Solo server, persona, metodo e data. Gli altri server ne vedono il numero (D65).
CREATE TABLE IF NOT EXISTS verify_vpn_storico (
    guild_id  BIGINT NOT NULL,
    user_id   BIGINT NOT NULL,
    metodo    TEXT,
    creato_il TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (guild_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_verify_vpn_storico_utente ON verify_vpn_storico (user_id);
