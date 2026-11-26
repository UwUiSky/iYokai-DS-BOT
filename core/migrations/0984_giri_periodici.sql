-- Blocco C (#10): stato dei giri periodici. Serve a non rifare tutti i lavori a ogni riavvio
-- (si riparte dall'ultimo giro riuscito) e a leggere lo stato in /salute. Nessun dato di persone.
CREATE TABLE IF NOT EXISTS giri_periodici (
    nome                 TEXT PRIMARY KEY,
    ultimo_giro_ok       TIMESTAMPTZ,
    ultimo_errore        TIMESTAMPTZ,
    errori_consecutivi   INTEGER NOT NULL DEFAULT 0,
    testo_errore         TEXT
);
