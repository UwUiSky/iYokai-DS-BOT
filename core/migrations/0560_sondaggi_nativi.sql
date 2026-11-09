-- D69 B23: sondaggi nativi di Discord che il bot deve seguire: quelli che iniziano più tardi (UTL-090) e quelli che si
-- chiudono a N voti (UTL-092). `voti` conta i voti ricevuti (nessun utente salvato). La riga sparisce alla fine del sondaggio.
CREATE TABLE IF NOT EXISTS sondaggi_nativi (
    id            BIGSERIAL PRIMARY KEY,
    guild_id      BIGINT NOT NULL,
    channel_id    BIGINT NOT NULL,
    message_id    BIGINT,
    autore_id     BIGINT NOT NULL,
    domanda       TEXT   NOT NULL,
    opzioni       TEXT[] NOT NULL,
    multipla      BOOLEAN NOT NULL DEFAULT FALSE,
    durata_ore    INT    NOT NULL CHECK (durata_ore BETWEEN 1 AND 768),
    discussione   BOOLEAN NOT NULL DEFAULT FALSE,
    chiudi_a_voti INT CHECK (chiudi_a_voti IS NULL OR chiudi_a_voti BETWEEN 1 AND 100000),
    voti          INT    NOT NULL DEFAULT 0,
    inizia_il     TIMESTAMPTZ,
    stato         TEXT   NOT NULL DEFAULT 'programmato' CHECK (stato IN ('programmato', 'aperto', 'chiuso')),
    creato_il     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_sondaggi_nativi_messaggio ON sondaggi_nativi (message_id) WHERE message_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_sondaggi_nativi_server ON sondaggi_nativi (guild_id, channel_id);
