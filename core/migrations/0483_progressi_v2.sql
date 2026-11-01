-- 23.17 (D51): missioni della settimana e del server, protezione della serie, pass di 90 giorni.
ALTER TABLE progress_serie ADD COLUMN IF NOT EXISTS ultima_at TIMESTAMPTZ;
ALTER TABLE progress_serie ADD COLUMN IF NOT EXISTS scudi INTEGER NOT NULL DEFAULT 0;
ALTER TABLE progress_serie ADD COLUMN IF NOT EXISTS scudi_usati INTEGER NOT NULL DEFAULT 0;
ALTER TABLE progress_serie ADD COLUMN IF NOT EXISTS promemoria BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE progress_serie ADD COLUMN IF NOT EXISTS promemoria_inviato_at TIMESTAMPTZ;

ALTER TABLE progress_stagione ADD COLUMN IF NOT EXISTS xp INTEGER NOT NULL DEFAULT 0;
ALTER TABLE progress_stagione ADD COLUMN IF NOT EXISTS premium BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE progress_stagione ADD COLUMN IF NOT EXISTS riscattati_premium INTEGER NOT NULL DEFAULT 0;

CREATE INDEX IF NOT EXISTS idx_progress_missioni_server ON progress_missioni (guild_id, giorno, chiave);

CREATE TABLE IF NOT EXISTS progress_server_riscatti (
    guild_id  BIGINT NOT NULL,
    user_id   BIGINT NOT NULL,
    settimana DATE NOT NULL,
    chiave    TEXT NOT NULL,
    PRIMARY KEY (guild_id, user_id, settimana, chiave)
);
