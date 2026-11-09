-- D69 B11: punti in più o in meno per membro (bonus), esclusioni dalla classifica (utente o ruolo), ingressi «finti»
-- (account troppo giovane o rientro). Il comando delle opzioni passa da `admin-moduli inviti` a `admin-inviti impostazioni`.
CREATE TABLE IF NOT EXISTS inviti_bonus (
    guild_id BIGINT NOT NULL,
    user_id  BIGINT NOT NULL,
    quanti   INT NOT NULL CHECK (quanti BETWEEN -100000 AND 100000),
    dato_da  BIGINT,
    PRIMARY KEY (guild_id, user_id)
);

CREATE TABLE IF NOT EXISTS inviti_esclusi (
    guild_id BIGINT NOT NULL,
    tipo     TEXT   NOT NULL CHECK (tipo IN ('utente', 'ruolo')),
    id       BIGINT NOT NULL,
    PRIMARY KEY (guild_id, tipo, id)
);

ALTER TABLE invite_joins ADD COLUMN IF NOT EXISTS finto BOOLEAN NOT NULL DEFAULT FALSE;

-- Percorsi di comando rinominati: la politica dei server, il registro modifiche e l'ultimo comando usato seguono il nome nuovo
-- (modello della 0488): un comando spento resta spento. Rilanciarla non cambia nulla.
UPDATE guild_config g
SET settings = jsonb_set(g.settings, '{policy_comandi_off}', (
    SELECT COALESCE(jsonb_agg(DISTINCT to_jsonb(COALESCE(m.nuovo, e.v))), '[]'::jsonb)
    FROM jsonb_array_elements_text(g.settings -> 'policy_comandi_off') AS e(v)
    LEFT JOIN (WITH m(vecchio, nuovo) AS (VALUES
        ('admin-moduli inviti', 'admin-inviti impostazioni')
    ) SELECT vecchio, nuovo FROM m) m ON m.vecchio = e.v))
WHERE jsonb_typeof(g.settings -> 'policy_comandi_off') = 'array';

UPDATE guild_config_history h
SET old_value = CASE WHEN h.old_value ~ '^\s*\[' THEN (
        SELECT COALESCE(jsonb_agg(DISTINCT to_jsonb(COALESCE(m.nuovo, e.v))), '[]'::jsonb)::text
        FROM jsonb_array_elements_text(h.old_value::jsonb) AS e(v)
        LEFT JOIN (WITH m(vecchio, nuovo) AS (VALUES
        ('admin-moduli inviti', 'admin-inviti impostazioni')
    ) SELECT vecchio, nuovo FROM m) m ON m.vecchio = e.v) ELSE h.old_value END,
    new_value = CASE WHEN h.new_value ~ '^\s*\[' THEN (
        SELECT COALESCE(jsonb_agg(DISTINCT to_jsonb(COALESCE(m.nuovo, e.v))), '[]'::jsonb)::text
        FROM jsonb_array_elements_text(h.new_value::jsonb) AS e(v)
        LEFT JOIN (WITH m(vecchio, nuovo) AS (VALUES
        ('admin-moduli inviti', 'admin-inviti impostazioni')
    ) SELECT vecchio, nuovo FROM m) m ON m.vecchio = e.v) ELSE h.new_value END
WHERE h.key_name = 'policy_comandi_off';

WITH m(vecchio, nuovo) AS (VALUES
        ('admin-moduli inviti', 'admin-inviti impostazioni')
)
UPDATE command_usage c
SET command_path = m.nuovo
FROM m
WHERE c.command_path = m.vecchio;
