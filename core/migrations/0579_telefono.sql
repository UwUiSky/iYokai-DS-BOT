-- #131 B12 (FUN-079): il telefono tra server. Un canale per server (e il webhook di una chiamata in corso, così al
-- riavvio si può togliere) e i blocchi di un server verso un utente o un altro server. Il consenso è nelle
-- impostazioni del server (`fun_telefono`, spento di base).
CREATE TABLE IF NOT EXISTS telefono_server (
    guild_id    BIGINT PRIMARY KEY,
    canale_id   BIGINT NOT NULL,
    webhook_id  BIGINT,
    aggiornato_il TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS telefono_blocchi (
    guild_id     BIGINT NOT NULL,
    tipo         TEXT NOT NULL CHECK (tipo IN ('utente', 'server')),
    bersaglio_id BIGINT NOT NULL,
    creato_il    TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (guild_id, tipo, bersaglio_id)
);
