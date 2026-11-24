-- UTL-110: quanti messaggi programmati con @everyone o @here ha inviato ogni server, giorno per giorno (tetto giornaliero).
CREATE TABLE IF NOT EXISTS everyone_invii (
    guild_id  BIGINT NOT NULL,
    giorno    DATE NOT NULL,
    conteggio INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (guild_id, giorno)
);
