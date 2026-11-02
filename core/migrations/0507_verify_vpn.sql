-- D64: VPN e proxy nella verifica web. Solo l'esito, il metodo che ha fatto scattare il blocco e la data:
-- mai l'IP. `eccezione` = un admin ha premuto «Lascia passare» per quella persona in quel server;
-- `da_storico` = passata perché altri server l'avevano già accettata (D65).
-- Le righe scadono (core/data_registry.py).
CREATE TABLE IF NOT EXISTS verify_vpn (
    guild_id    BIGINT NOT NULL,
    user_id     BIGINT NOT NULL,
    metodo      TEXT,
    esito       TEXT NOT NULL DEFAULT 'bloccato' CHECK (esito IN ('bloccato', 'eccezione', 'da_storico')),
    creato_il   TIMESTAMPTZ NOT NULL DEFAULT now(),
    avvisato_il TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (guild_id, user_id)
);
