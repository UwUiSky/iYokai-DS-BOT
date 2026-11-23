-- UTL-228 (D111): richiesta di azzerare tutti i dati del bot per un server, con 30 giorni di ritardo.
CREATE TABLE IF NOT EXISTS richieste_azzeramento (
    guild_id             BIGINT PRIMARY KEY,
    richiesto_da         BIGINT      NOT NULL,
    proprietario_id      BIGINT      NOT NULL,   -- chi possedeva il server quando si è confermato
    richiesta_il         TIMESTAMPTZ NOT NULL DEFAULT now(),
    esegui_il            TIMESTAMPTZ NOT NULL,
    stato                TEXT        NOT NULL DEFAULT 'attiva' CHECK (stato IN ('attiva', 'sospesa')),
    azione_preavviso_id  BIGINT,
    azione_esegui_id     BIGINT
);
