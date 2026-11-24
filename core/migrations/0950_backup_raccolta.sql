-- BKP-022/023 (D127, D130, #121): raccolta pubblica dei modelli di server, con revisione dell'owner e voti.
-- La struttura non contiene ID, membri, messaggi né dati personali (si ricostruisce campo per campo prima di salvarla).
CREATE TABLE IF NOT EXISTS backup_raccolta (
    id            BIGSERIAL PRIMARY KEY,
    guild_id      BIGINT NOT NULL,
    proposto_da   BIGINT NOT NULL,
    nome          TEXT NOT NULL CHECK (char_length(nome) BETWEEN 3 AND 60),
    descrizione   TEXT NOT NULL DEFAULT '' CHECK (char_length(descrizione) <= 300),
    lingua        TEXT NOT NULL DEFAULT 'it',
    struttura     JSONB NOT NULL,
    stato         TEXT NOT NULL DEFAULT 'revisione' CHECK (stato IN ('revisione', 'approvato', 'rifiutato')),
    deciso_da     BIGINT,
    deciso_il     TIMESTAMPTZ,
    creato_il     TIMESTAMPTZ NOT NULL DEFAULT now(),
    modificato_il TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS backup_raccolta_stato ON backup_raccolta (stato, creato_il DESC);
CREATE INDEX IF NOT EXISTS backup_raccolta_guild ON backup_raccolta (guild_id);
CREATE TABLE IF NOT EXISTS backup_raccolta_voti (
    modello_id BIGINT NOT NULL REFERENCES backup_raccolta (id) ON DELETE CASCADE,
    user_id    BIGINT NOT NULL,
    creato_il  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (modello_id, user_id)
);
CREATE INDEX IF NOT EXISTS backup_raccolta_voti_utente ON backup_raccolta_voti (user_id);
