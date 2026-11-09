-- #131 B1 (D70): chi non vuole ricevere le GIF di azione. Un interruttore per utente («blocca tutti») e
-- l'elenco di chi è bloccato (massimo 25 per utente, tetto nel codice). Valgono in ogni server.
CREATE TABLE IF NOT EXISTS gif_privacy (
    user_id     BIGINT PRIMARY KEY,
    blocca_tutti BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE TABLE IF NOT EXISTS gif_blocchi (
    user_id     BIGINT NOT NULL,
    bloccato_id BIGINT NOT NULL,
    creato_il   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, bloccato_id)
);
