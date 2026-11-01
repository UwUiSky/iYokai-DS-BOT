-- 23.17 (D51): le serie scritte con la regola di prima hanno solo il giorno. Diamo loro mezzogiorno UTC
-- di quel giorno: così una riscossione di oggi, a qualsiasi ora, cade tra 12 e 36 ore e la serie continua.
UPDATE progress_serie
SET ultima_at = (ultimo_giorno + time '12:00') AT TIME ZONE 'UTC'
WHERE ultima_at IS NULL AND ultimo_giorno IS NOT NULL;
