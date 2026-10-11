-- #86 (NF-15): impostazioni dei livelli per server. Una riga di opzioni per
-- server (senza riga valgono i valori di prima) e le regole di canali e ruoli
-- (esclusi o con moltiplicatore). Nessun dato personale.
CREATE TABLE IF NOT EXISTS leveling_settings (
    guild_id               BIGINT PRIMARY KEY,
    text_xp                INT     NOT NULL DEFAULT 15  CHECK (text_xp BETWEEN 1 AND 100),
    text_cooldown_seconds  INT     NOT NULL DEFAULT 60  CHECK (text_cooldown_seconds BETWEEN 10 AND 600),
    voice_xp_per_minute    INT     NOT NULL DEFAULT 5   CHECK (voice_xp_per_minute BETWEEN 0 AND 50),
    voice_coins_per_minute INT     NOT NULL DEFAULT 2   CHECK (voice_coins_per_minute BETWEEN 0 AND 50),
    levelup_mode           TEXT    NOT NULL DEFAULT 'canale_corrente'
                           CHECK (levelup_mode IN ('spento', 'canale_corrente', 'dm', 'canale_scelto')),
    levelup_channel_id     BIGINT,
    levelup_min_level      INT     NOT NULL DEFAULT 0   CHECK (levelup_min_level BETWEEN 0 AND 1000),
    levelup_every          INT     NOT NULL DEFAULT 1   CHECK (levelup_every BETWEEN 1 AND 100),
    levelup_only_rewards   BOOLEAN NOT NULL DEFAULT FALSE,
    reward_mode            TEXT    NOT NULL DEFAULT 'accumula'
                           CHECK (reward_mode IN ('accumula', 'sostituisci')),
    multiplier_mode        TEXT    NOT NULL DEFAULT 'somma'
                           CHECK (multiplier_mode IN ('somma', 'massimo'))
);

CREATE TABLE IF NOT EXISTS leveling_xp_rules (
    guild_id  BIGINT        NOT NULL,
    kind      TEXT          NOT NULL
              CHECK (kind IN ('canale_escluso', 'ruolo_escluso', 'mult_canale', 'mult_ruolo')),
    target_id BIGINT        NOT NULL,
    factor    NUMERIC(5, 2) CHECK (factor IS NULL OR factor BETWEEN 0.1 AND 10),
    PRIMARY KEY (guild_id, kind, target_id)
);
