-- M 9.10: il decadimento settimanale dei coin personali non deve
-- toccare chi è arrivato da meno di una settimana intera. Serve sapere
-- quando è nata la riga. Le righe già presenti restano senza data
-- (NULL) e valgono come "vecchie": continuano a decadere come prima.
-- Le righe nuove prendono la data da sole, qualunque sia la scrittura
-- che le crea.
ALTER TABLE leveling_totals ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ;
ALTER TABLE leveling_totals ALTER COLUMN created_at SET DEFAULT now();
