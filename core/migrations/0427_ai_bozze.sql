-- AI-R-107 (r12): bozze di codice per le richieste di comandi approvate dall'owner. Una riga per richiesta.
CREATE TABLE IF NOT EXISTS ai_bozze (
    request_id INTEGER PRIMARY KEY,
    stato      TEXT NOT NULL DEFAULT 'pronta',  -- pronta | pr_aperta | errore
    bozza      TEXT NOT NULL DEFAULT '',
    pr_url     TEXT,
    errore     TEXT,
    creato_il  TIMESTAMPTZ NOT NULL DEFAULT now()
);
