-- MUS-014 (#126): playlist per genere scelte dall'owner del bot (non di un server). Il menu `/music genere`
-- le mostra a tutti. Tetti (25 generi, 25 playlist per genere, 200 in tutto) nel codice, sotto un lock.
-- Nessuna pulizia automatica: la tabella cresce solo a mano e ha un tetto.
CREATE TABLE IF NOT EXISTS music_genere_playlist (
    id          BIGSERIAL   PRIMARY KEY,
    genere      TEXT        NOT NULL CHECK (char_length(genere) BETWEEN 2 AND 30),
    titolo      TEXT        NOT NULL CHECK (char_length(titolo) BETWEEN 1 AND 80),
    link        TEXT        NOT NULL CHECK (char_length(link) <= 300),
    aggiunta_da BIGINT      NOT NULL,
    aggiunta_il TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS music_genere_playlist_titolo ON music_genere_playlist (lower(genere), lower(titolo));
CREATE UNIQUE INDEX IF NOT EXISTS music_genere_playlist_link ON music_genere_playlist (lower(genere), link);
