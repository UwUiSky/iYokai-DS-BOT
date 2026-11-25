-- Blocco A, voce 6: lo stato che non deve sparire a un riavvio sta nel database.
-- 1) I link del ripristino (`state` firmato) si usano una volta sola: il nonce è una riga. Un link già andato a buon
--    fine resta bloccato anche dopo un riavvio; uno in corso da più di 5 minuti (processo morto) si può riprendere.
-- 2) I limiti del pannello che proteggono Discord o i segreti (marchio, sincronia dei permessi, copia dei dati).
CREATE TABLE IF NOT EXISTS restore_nonce (
    nonce    TEXT PRIMARY KEY,
    stato    TEXT NOT NULL CHECK (stato IN ('in_corso', 'usato')),
    preso_il TIMESTAMPTZ NOT NULL DEFAULT now(),
    scade_il TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_restore_nonce_scadenza ON restore_nonce (scade_il);

CREATE TABLE IF NOT EXISTS pannello_limiti (
    nome      TEXT NOT NULL,
    ambito    TEXT NOT NULL CHECK (ambito IN ('server', 'utente')),
    soggetto  BIGINT NOT NULL,
    colpito_il TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_pannello_limiti ON pannello_limiti (nome, soggetto, colpito_il);
