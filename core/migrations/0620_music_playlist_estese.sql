-- #126 (r4mus): MUS-072/083 link di origine, MUS-084 codice di condivisione, MUS-081 playlist del server,
-- MUS-086 playlist a più mani.
ALTER TABLE music_playlists ADD COLUMN IF NOT EXISTS source_url TEXT CHECK (source_url IS NULL OR char_length(source_url) <= 300);
ALTER TABLE music_playlists ADD COLUMN IF NOT EXISTS share_code TEXT CHECK (share_code IS NULL OR char_length(share_code) = 8);
CREATE UNIQUE INDEX IF NOT EXISTS music_playlists_share_code_uq ON music_playlists (share_code) WHERE share_code IS NOT NULL;

CREATE TABLE IF NOT EXISTS music_guild_playlists (
    guild_id    BIGINT NOT NULL,
    name        TEXT NOT NULL CHECK (char_length(name) BETWEEN 1 AND 50),
    tracks      JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_by  BIGINT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (guild_id, name)
);

CREATE TABLE IF NOT EXISTS music_playlist_collabs (
    owner_id    BIGINT NOT NULL,
    name        TEXT NOT NULL,
    user_id     BIGINT NOT NULL,
    added_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (owner_id, name, user_id),
    FOREIGN KEY (owner_id, name) REFERENCES music_playlists (user_id, name) ON DELETE CASCADE ON UPDATE CASCADE
);
CREATE INDEX IF NOT EXISTS music_playlist_collabs_user_idx ON music_playlist_collabs (user_id);
