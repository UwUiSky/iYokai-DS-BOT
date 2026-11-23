-- r1doc (LIV-046): un ruolo premio può chiedere anche un livello vocale minimo (0 = nessuna richiesta).
ALTER TABLE level_reward_roles
    ADD COLUMN IF NOT EXISTS livello_vocale INTEGER NOT NULL DEFAULT 0 CHECK (livello_vocale BETWEEN 0 AND 1000);
