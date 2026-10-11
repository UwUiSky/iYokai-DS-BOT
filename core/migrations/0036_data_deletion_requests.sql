-- NF-04 (#37, #75): richieste di cancellazione dei dati di un utente e loro esito.
-- Una sola richiesta in attesa per utente. `esito` è il rapporto della
-- cancellazione (righe cancellate, anonimizzate, conservate e perché), senza
-- dati personali: serve a dimostrare che cosa è stato fatto.
CREATE TABLE IF NOT EXISTS data_deletion_requests (
    id            BIGSERIAL PRIMARY KEY,
    user_id       BIGINT NOT NULL,
    motivo        TEXT,
    stato         TEXT NOT NULL DEFAULT 'in_attesa'
                  CHECK (stato IN ('in_attesa', 'eseguita', 'rifiutata')),
    richiesta_il  TIMESTAMPTZ NOT NULL DEFAULT now(),
    deciso_il     TIMESTAMPTZ,
    deciso_da     BIGINT,
    esito         JSONB
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_data_deletion_in_attesa
    ON data_deletion_requests (user_id) WHERE stato = 'in_attesa';
CREATE INDEX IF NOT EXISTS idx_data_deletion_stato
    ON data_deletion_requests (stato, richiesta_il);
