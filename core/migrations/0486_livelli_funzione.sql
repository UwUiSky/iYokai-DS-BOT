-- D57: il livello di abbonamento di ogni funzione (gratuito, premium, VIP 5, VIP 20).
-- Una riga solo per le funzioni non gratuite: senza riga il livello è «gratuito».
CREATE TABLE IF NOT EXISTS livelli_funzione (
    funzione     TEXT PRIMARY KEY,
    livello      TEXT NOT NULL CHECK (livello IN ('premium', 'vip5', 'vip20')),
    aggiornato_il TIMESTAMPTZ NOT NULL DEFAULT now()
);
