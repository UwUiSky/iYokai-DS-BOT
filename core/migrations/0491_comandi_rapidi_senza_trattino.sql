-- I due comandi rapidi perdono il trattino iniziale (/-cerca-comando → /cerca-comando, /-chiedi → /chiedi,
-- scelta dell'owner 01/11). Stessi tre posti della 0488; rilanciarla non cambia nulla.

-- 1. Politica dei comandi: l'elenco dei comandi spenti di ogni server.
UPDATE guild_config g
SET settings = jsonb_set(g.settings, '{policy_comandi_off}', (
    SELECT COALESCE(jsonb_agg(DISTINCT to_jsonb(COALESCE(m.nuovo, e.v))), '[]'::jsonb)
    FROM jsonb_array_elements_text(g.settings -> 'policy_comandi_off') AS e(v)
    LEFT JOIN (WITH m(vecchio, nuovo) AS (VALUES
        ('-cerca-comando', 'cerca-comando'),
        ('-chiedi', 'chiedi')
    )
        SELECT vecchio, nuovo FROM m) m ON m.vecchio = e.v
))
WHERE jsonb_typeof(g.settings -> 'policy_comandi_off') = 'array';

-- 2. Registro modifiche: valori vecchio e nuovo dell'elenco (testo JSON), così il ripristino non riaccende nulla.
UPDATE guild_config_history h
SET old_value = CASE WHEN h.old_value ~ '^\s*\[' THEN (
        SELECT COALESCE(jsonb_agg(DISTINCT to_jsonb(COALESCE(m.nuovo, e.v))), '[]'::jsonb)::text
        FROM jsonb_array_elements_text(h.old_value::jsonb) AS e(v)
        LEFT JOIN (WITH m(vecchio, nuovo) AS (VALUES
        ('-cerca-comando', 'cerca-comando'),
        ('-chiedi', 'chiedi')
    )
            SELECT vecchio, nuovo FROM m) m ON m.vecchio = e.v) ELSE h.old_value END,
    new_value = CASE WHEN h.new_value ~ '^\s*\[' THEN (
        SELECT COALESCE(jsonb_agg(DISTINCT to_jsonb(COALESCE(m.nuovo, e.v))), '[]'::jsonb)::text
        FROM jsonb_array_elements_text(h.new_value::jsonb) AS e(v)
        LEFT JOIN (WITH m(vecchio, nuovo) AS (VALUES
        ('-cerca-comando', 'cerca-comando'),
        ('-chiedi', 'chiedi')
    )
            SELECT vecchio, nuovo FROM m) m ON m.vecchio = e.v) ELSE h.new_value END
WHERE h.key_name = 'policy_comandi_off';

-- 3. Ultimo comando usato.
WITH m(vecchio, nuovo) AS (VALUES
    ('-cerca-comando', 'cerca-comando'),
    ('-chiedi', 'chiedi')
)
UPDATE command_usage c
SET command_path = m.nuovo
FROM m
WHERE c.command_path = m.vecchio;
