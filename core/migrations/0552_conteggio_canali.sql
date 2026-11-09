-- D69 B14: il gioco del conteggio passa da un canale per server (`counting_games`) a più canali (max 10) con modo
-- (decimale, binario, romani, lettere), filtro, punizione e ruolo dell'ultimo. Le righe di `counting_games` si copiano
-- nella tabella nuova (la vecchia resta, non si legge più). Punteggi per membro e blocchi a tempo.
-- Il comando passa da `admin-moduli conteggio` a `admin-giochi conteggio canale`.
CREATE TABLE IF NOT EXISTS conteggio_canali (
    guild_id         BIGINT NOT NULL,
    channel_id       BIGINT NOT NULL,
    modo             TEXT   NOT NULL DEFAULT 'decimale' CHECK (modo IN ('decimale', 'binario', 'romani', 'lettere')),
    filtro           TEXT   NOT NULL DEFAULT 'solo_numero' CHECK (filtro IN ('solo_numero', 'con_testo')),
    current          INT    NOT NULL DEFAULT 0 CHECK (current >= 0),
    last_user_id     BIGINT,
    best             INT    NOT NULL DEFAULT 0 CHECK (best >= 0),
    punizione_minuti INT    NOT NULL DEFAULT 0 CHECK (punizione_minuti BETWEEN 0 AND 1440),
    ruolo_ultimo     BIGINT,
    PRIMARY KEY (guild_id, channel_id)
);
INSERT INTO conteggio_canali (guild_id, channel_id, current, last_user_id, best)
    SELECT guild_id, channel_id, current, last_user_id, best FROM counting_games
    ON CONFLICT (guild_id, channel_id) DO NOTHING;

CREATE TABLE IF NOT EXISTS conteggio_punteggi (
    guild_id   BIGINT NOT NULL,
    channel_id BIGINT NOT NULL,
    user_id    BIGINT NOT NULL,
    giusti     INT NOT NULL DEFAULT 0,
    sbagliati  INT NOT NULL DEFAULT 0,
    PRIMARY KEY (guild_id, channel_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_conteggio_punteggi_utente ON conteggio_punteggi (user_id);

CREATE TABLE IF NOT EXISTS conteggio_blocchi (
    guild_id   BIGINT NOT NULL,
    channel_id BIGINT NOT NULL,
    user_id    BIGINT NOT NULL,
    scade_il   TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (guild_id, channel_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_conteggio_blocchi_scadenza ON conteggio_blocchi (scade_il);

-- Percorsi di comando rinominati: la politica dei server, il registro modifiche e l'ultimo comando usato seguono il nome nuovo
-- (modello della 0488): un comando spento resta spento. Rilanciarla non cambia nulla.
UPDATE guild_config g
SET settings = jsonb_set(g.settings, '{policy_comandi_off}', (
    SELECT COALESCE(jsonb_agg(DISTINCT to_jsonb(COALESCE(m.nuovo, e.v))), '[]'::jsonb)
    FROM jsonb_array_elements_text(g.settings -> 'policy_comandi_off') AS e(v)
    LEFT JOIN (WITH m(vecchio, nuovo) AS (VALUES
        ('admin-moduli conteggio', 'admin-giochi conteggio canale')
    ) SELECT vecchio, nuovo FROM m) m ON m.vecchio = e.v))
WHERE jsonb_typeof(g.settings -> 'policy_comandi_off') = 'array';

UPDATE guild_config_history h
SET old_value = CASE WHEN h.old_value ~ '^\s*\[' THEN (
        SELECT COALESCE(jsonb_agg(DISTINCT to_jsonb(COALESCE(m.nuovo, e.v))), '[]'::jsonb)::text
        FROM jsonb_array_elements_text(h.old_value::jsonb) AS e(v)
        LEFT JOIN (WITH m(vecchio, nuovo) AS (VALUES
        ('admin-moduli conteggio', 'admin-giochi conteggio canale')
    ) SELECT vecchio, nuovo FROM m) m ON m.vecchio = e.v) ELSE h.old_value END,
    new_value = CASE WHEN h.new_value ~ '^\s*\[' THEN (
        SELECT COALESCE(jsonb_agg(DISTINCT to_jsonb(COALESCE(m.nuovo, e.v))), '[]'::jsonb)::text
        FROM jsonb_array_elements_text(h.new_value::jsonb) AS e(v)
        LEFT JOIN (WITH m(vecchio, nuovo) AS (VALUES
        ('admin-moduli conteggio', 'admin-giochi conteggio canale')
    ) SELECT vecchio, nuovo FROM m) m ON m.vecchio = e.v) ELSE h.new_value END
WHERE h.key_name = 'policy_comandi_off';

WITH m(vecchio, nuovo) AS (VALUES
        ('admin-moduli conteggio', 'admin-giochi conteggio canale')
)
UPDATE command_usage c
SET command_path = m.nuovo
FROM m
WHERE c.command_path = m.vecchio;
