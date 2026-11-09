-- #131 B12 (FUN-079): il registro delle chiamate. Solo i due server, l'ora e la durata: mai il testo dei messaggi
-- né chi li ha scritti. Si tiene 14 giorni (core/data_registry.py).
CREATE TABLE IF NOT EXISTS telefono_registro (
    id               BIGSERIAL PRIMARY KEY,
    guild_a          BIGINT NOT NULL,
    guild_b          BIGINT NOT NULL,
    iniziata_il      TIMESTAMPTZ NOT NULL,
    durata_secondi   INTEGER NOT NULL DEFAULT 0,
    fine             TEXT NOT NULL DEFAULT '',
    segnalata        BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE INDEX IF NOT EXISTS telefono_registro_a ON telefono_registro (guild_a, iniziata_il DESC);
CREATE INDEX IF NOT EXISTS telefono_registro_b ON telefono_registro (guild_b, iniziata_il DESC);
