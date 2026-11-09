-- #131 B10 (D70): segnalazioni dei post di Lemmy mostrati da `/immagini post`. Una riga per persona e per post;
-- con 3 persone diverse il post non si mostra più (il conteggio è nel codice).
CREATE TABLE IF NOT EXISTS immagini_segnalazioni (
    post_key  TEXT NOT NULL,
    user_id   BIGINT NOT NULL,
    guild_id  BIGINT NOT NULL,
    creato_il TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (post_key, user_id)
);
