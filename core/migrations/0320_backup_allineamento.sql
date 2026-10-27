-- 11.17: il Creator riallinea ogni coppia a intervalli; qui restano l'ora e l'esito dell'ultimo giro.
ALTER TABLE backup_pairs ADD COLUMN IF NOT EXISTS ultimo_allineamento TIMESTAMPTZ;
ALTER TABLE backup_pairs ADD COLUMN IF NOT EXISTS esito_allineamento TEXT;
