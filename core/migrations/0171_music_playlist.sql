-- NF-19 (#90), MUS-082: playlist salvate dagli utenti, valide in ogni server.
-- tracks = elenco JSON di {"title", "uri", "length", "encoded"} (al massimo 200).
CREATE TABLE IF NOT EXISTS music_playlists (
    user_id     BIGINT NOT NULL,
    name        TEXT NOT NULL CHECK (char_length(name) BETWEEN 1 AND 50),
    tracks      JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, name)
);
