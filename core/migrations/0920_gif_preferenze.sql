-- FUN-138 (D124): preferenze delle GIF di ogni utente (genere dei personaggi, preferiti, anime o no).
-- Una riga per persona, solo se ha scelto qualcosa. I preferiti sono id del catalogo data/gif_personaggi.json (massimo 10, tetto nel codice).
CREATE TABLE IF NOT EXISTS gif_preferenze (
    user_id      BIGINT PRIMARY KEY,
    genere       TEXT NOT NULL DEFAULT 'qualsiasi',
    tipo         TEXT NOT NULL DEFAULT 'entrambi',
    personaggi   TEXT[] NOT NULL DEFAULT '{}',
    aggiornato_il TIMESTAMPTZ NOT NULL DEFAULT now()
);
