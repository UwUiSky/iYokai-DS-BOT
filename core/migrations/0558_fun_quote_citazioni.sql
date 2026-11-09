-- D69 B16: `/fun quote` diventa `/fun citazioni caso fonte:famose`. La politica dei server, il registro modifiche e
-- l'ultimo comando usato seguono il nome nuovo.
-- Percorso rinominato (modello della 0557). Rilanciarla non cambia nulla.
UPDATE guild_config g
SET settings = jsonb_set(g.settings, '{policy_comandi_off}', (
    SELECT COALESCE(jsonb_agg(DISTINCT to_jsonb(COALESCE(m.nuovo, e.v))), '[]'::jsonb)
    FROM jsonb_array_elements_text(g.settings -> 'policy_comandi_off') AS e(v)
    LEFT JOIN (WITH m(vecchio, nuovo) AS (VALUES
        ('fun quote', 'fun citazioni caso')
    ) SELECT vecchio, nuovo FROM m) m ON m.vecchio = e.v))
WHERE jsonb_typeof(g.settings -> 'policy_comandi_off') = 'array';

UPDATE guild_config_history h
SET old_value = CASE WHEN h.old_value ~ '^\s*\[' THEN (
        SELECT COALESCE(jsonb_agg(DISTINCT to_jsonb(COALESCE(m.nuovo, e.v))), '[]'::jsonb)::text
        FROM jsonb_array_elements_text(h.old_value::jsonb) AS e(v)
        LEFT JOIN (WITH m(vecchio, nuovo) AS (VALUES
        ('fun quote', 'fun citazioni caso')
    ) SELECT vecchio, nuovo FROM m) m ON m.vecchio = e.v) ELSE h.old_value END,
    new_value = CASE WHEN h.new_value ~ '^\s*\[' THEN (
        SELECT COALESCE(jsonb_agg(DISTINCT to_jsonb(COALESCE(m.nuovo, e.v))), '[]'::jsonb)::text
        FROM jsonb_array_elements_text(h.new_value::jsonb) AS e(v)
        LEFT JOIN (WITH m(vecchio, nuovo) AS (VALUES
        ('fun quote', 'fun citazioni caso')
    ) SELECT vecchio, nuovo FROM m) m ON m.vecchio = e.v) ELSE h.new_value END
WHERE h.key_name = 'policy_comandi_off';

WITH m(vecchio, nuovo) AS (VALUES
        ('fun quote', 'fun citazioni caso')
)
UPDATE command_usage c
SET command_path = m.nuovo
FROM m
WHERE c.command_path = m.vecchio;
