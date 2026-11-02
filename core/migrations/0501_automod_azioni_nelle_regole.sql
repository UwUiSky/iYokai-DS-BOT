-- D63: copia una volta le azioni di prima (settings->'actions' e mute_duration_seconds) in righe automod_regole
-- di tipo 'filtro'. Stesse punizioni, nell'ordine di prima (delete, warn, mute, kick, ban). Una riga con
-- azioni vuote resta vuota: l'admin aveva tolto ogni azione. Si può rieseguire senza danni.
INSERT INTO automod_regole (guild_id, chiave, tipo, nome, azioni)
SELECT c.guild_id, a.key, 'filtro', left(a.key, 32),
       COALESCE((
           SELECT jsonb_agg(
                      CASE v.n
                          WHEN 'delete' THEN jsonb_build_object('t', 'cancella')
                          WHEN 'mute' THEN jsonb_build_object(
                              't', 'timeout',
                              'secondi', LEAST(GREATEST(COALESCE((c.settings->>'mute_duration_seconds')::bigint, 600), 1), 2419200))
                          ELSE jsonb_build_object('t', v.n)
                      END
                      ORDER BY v.ord)
           FROM (VALUES ('delete', 1), ('warn', 2), ('mute', 3), ('kick', 4), ('ban', 5)) AS v(n, ord)
           WHERE a.value ? v.n
       ), '[]'::jsonb)
FROM automod_advanced_config c, LATERAL jsonb_each(c.settings->'actions') AS a
WHERE jsonb_typeof(c.settings->'actions') = 'object' AND jsonb_typeof(a.value) = 'array'
ON CONFLICT (guild_id, chiave) DO NOTHING;
