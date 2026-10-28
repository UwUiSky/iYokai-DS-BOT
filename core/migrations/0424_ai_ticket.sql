-- NF-24 (r12): prima risposta automatica nei ticket, per pannello; un solo messaggio automatico per ticket.
CREATE TABLE IF NOT EXISTS ai_ticket_pannelli (
    guild_id       BIGINT  NOT NULL,
    panel_id       INTEGER NOT NULL,
    prima_risposta BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (guild_id, panel_id)
);
CREATE TABLE IF NOT EXISTS ai_ticket_risposte (
    channel_id BIGINT PRIMARY KEY,
    guild_id   BIGINT NOT NULL,
    creato_il  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ai_ticket_risposte_guild ON ai_ticket_risposte (guild_id);
