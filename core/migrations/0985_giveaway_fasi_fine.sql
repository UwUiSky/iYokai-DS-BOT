-- Blocco C (seri di stabilità): la fine di un giveaway a stati, così un errore non perde il premio in silenzio.
-- estrazione = scaduto, i vincitori non sono ancora stati scelti; annuncio = scelti, l'annuncio non è ancora partito;
-- fatto = annunciato; fallito = troppi tentativi (lo staff lo vede nel log e può rifarlo con il reroll).
-- I giveaway già finiti restano con fase NULL: non si toccano.
ALTER TABLE giveaways ADD COLUMN IF NOT EXISTS fase_fine TEXT;
ALTER TABLE giveaways DROP CONSTRAINT IF EXISTS giveaways_fase_fine_check;
ALTER TABLE giveaways ADD CONSTRAINT giveaways_fase_fine_check
    CHECK (fase_fine IS NULL OR fase_fine IN ('estrazione', 'annuncio', 'fatto', 'fallito'));
ALTER TABLE giveaways ADD COLUMN IF NOT EXISTS tentativi_fine INTEGER NOT NULL DEFAULT 0;
CREATE INDEX IF NOT EXISTS idx_giveaways_fine_in_corso ON giveaways (id) WHERE fase_fine IN ('estrazione', 'annuncio');
