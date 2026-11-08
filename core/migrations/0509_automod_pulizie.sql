-- D63 (AMD-073, 074): pulizia di un canale a intervalli. Una riga per canale: ogni quanto, quali messaggi, se anche
-- i fissati, se è accesa e quando è partito l'ultimo giro. La riga si cancella con il canale (on_guild_channel_delete).
CREATE TABLE IF NOT EXISTS automod_pulizie (
    guild_id     BIGINT NOT NULL,
    canale_id    BIGINT NOT NULL,
    ogni_secondi INTEGER NOT NULL CHECK (ogni_secondi BETWEEN 3600 AND 2592000),
    tipo         TEXT NOT NULL DEFAULT 'tutti' CHECK (tipo IN ('persone', 'bot', 'link', 'inviti', 'allegati', 'tutti')),
    fissati      BOOLEAN NOT NULL DEFAULT FALSE,
    attiva       BOOLEAN NOT NULL DEFAULT TRUE,
    ultimo_giro  TIMESTAMPTZ NOT NULL DEFAULT now(),
    creata_da    BIGINT,
    creata_il    TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (guild_id, canale_id)
);
CREATE INDEX IF NOT EXISTS idx_automod_pulizie_dovute ON automod_pulizie (attiva, ultimo_giro);
