-- D56: l'elenco dei promemoria del server è per lo staff, quindi passa da `/utility reminder server`
-- (gruppo per tutti) a `/messaggi promemoria`. Come la 0485: politica dei comandi, registro modifiche
-- e ultimo comando usato seguono il nome nuovo. Rilanciarla non cambia nulla.

-- 1. Politica dei comandi: l'elenco dei comandi spenti di ogni server.
UPDATE guild_config g
SET settings = jsonb_set(g.settings, '{policy_comandi_off}', (
    SELECT COALESCE(jsonb_agg(DISTINCT to_jsonb(
        CASE WHEN e.v = 'utility reminder server' THEN 'messaggi promemoria' ELSE e.v END)), '[]'::jsonb)
    FROM jsonb_array_elements_text(g.settings -> 'policy_comandi_off') AS e(v)
))
WHERE jsonb_typeof(g.settings -> 'policy_comandi_off') = 'array'
  AND g.settings -> 'policy_comandi_off' ? 'utility reminder server';

-- 2. Registro modifiche: valori vecchio e nuovo dell'elenco (testo JSON).
UPDATE guild_config_history h
SET old_value = CASE WHEN h.old_value ~ '^\s*\[' THEN (
        SELECT COALESCE(jsonb_agg(DISTINCT to_jsonb(
            CASE WHEN e.v = 'utility reminder server' THEN 'messaggi promemoria' ELSE e.v END)), '[]'::jsonb)::text
        FROM jsonb_array_elements_text(h.old_value::jsonb) AS e(v)) ELSE h.old_value END,
    new_value = CASE WHEN h.new_value ~ '^\s*\[' THEN (
        SELECT COALESCE(jsonb_agg(DISTINCT to_jsonb(
            CASE WHEN e.v = 'utility reminder server' THEN 'messaggi promemoria' ELSE e.v END)), '[]'::jsonb)::text
        FROM jsonb_array_elements_text(h.new_value::jsonb) AS e(v)) ELSE h.new_value END
WHERE h.key_name = 'policy_comandi_off'
  AND (h.old_value LIKE '%"utility reminder server"%' OR h.new_value LIKE '%"utility reminder server"%');

-- 3. Ultimo comando usato.
UPDATE command_usage SET command_path = 'messaggi promemoria' WHERE command_path = 'utility reminder server';
