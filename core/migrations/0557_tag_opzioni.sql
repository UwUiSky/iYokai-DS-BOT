-- D69 B19-B21: tag con opzioni di comportamento (permesso, bersaglio, cancella l'innesco, dove rispondere, reazioni,
-- cancellazione, solo NSFW, anche se modificato), risposte con pesi, testo fino a 4000 caratteri, gruppi di tag e
-- pacchetti da condividere (codice valido 7 giorni).
-- I comandi passano sotto `/tag usa` e `/admin-tag tag|risposte`: la politica dei server segue il nome nuovo.
ALTER TABLE custom_commands DROP CONSTRAINT IF EXISTS custom_commands_response_check;
ALTER TABLE custom_commands ADD CONSTRAINT custom_commands_response_check CHECK (char_length(response) BETWEEN 1 AND 4000);
ALTER TABLE custom_commands
    ADD COLUMN IF NOT EXISTS permesso         TEXT,
    ADD COLUMN IF NOT EXISTS bersaglio        BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS cancella_innesco BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS invio            TEXT NOT NULL DEFAULT 'canale',
    ADD COLUMN IF NOT EXISTS canale_id        BIGINT,
    ADD COLUMN IF NOT EXISTS reazioni         TEXT[] NOT NULL DEFAULT '{}',
    ADD COLUMN IF NOT EXISTS si_cancella_dopo INT,
    ADD COLUMN IF NOT EXISTS cancella_messaggi INT,
    ADD COLUMN IF NOT EXISTS solo_nsfw        BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS anche_modificati BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS gruppo           TEXT;
ALTER TABLE custom_commands DROP CONSTRAINT IF EXISTS custom_commands_invio_check;
ALTER TABLE custom_commands ADD CONSTRAINT custom_commands_invio_check CHECK (invio IN ('canale', 'privato', 'altro'));
ALTER TABLE custom_commands DROP CONSTRAINT IF EXISTS custom_commands_dopo_check;
ALTER TABLE custom_commands ADD CONSTRAINT custom_commands_dopo_check
    CHECK ((si_cancella_dopo IS NULL OR si_cancella_dopo BETWEEN 5 AND 3600)
       AND (cancella_messaggi IS NULL OR cancella_messaggi BETWEEN 1 AND 100)
       AND cardinality(reazioni) <= 5
       AND (gruppo IS NULL OR char_length(gruppo) BETWEEN 1 AND 32));

CREATE TABLE IF NOT EXISTS custom_command_risposte (
    guild_id BIGINT NOT NULL,
    name     TEXT NOT NULL,
    pos      SMALLINT NOT NULL CHECK (pos BETWEEN 1 AND 5),
    peso     SMALLINT NOT NULL DEFAULT 1 CHECK (peso BETWEEN 1 AND 99),
    testo    TEXT NOT NULL CHECK (char_length(testo) BETWEEN 1 AND 4000),
    PRIMARY KEY (guild_id, name, pos),
    FOREIGN KEY (guild_id, name) REFERENCES custom_commands (guild_id, name) ON DELETE CASCADE ON UPDATE CASCADE
);

CREATE TABLE IF NOT EXISTS tag_gruppi (
    guild_id BIGINT NOT NULL,
    gruppo   TEXT NOT NULL CHECK (char_length(gruppo) BETWEEN 1 AND 32),
    canale_id BIGINT,
    ruolo_id  BIGINT,
    PRIMARY KEY (guild_id, gruppo)
);

CREATE TABLE IF NOT EXISTS tag_pacchetti (
    codice    TEXT PRIMARY KEY CHECK (char_length(codice) BETWEEN 6 AND 16),
    guild_id  BIGINT NOT NULL,
    dati      JSONB NOT NULL,
    creato_da BIGINT,
    scade_il  TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tag_pacchetti_scadenza ON tag_pacchetti (scade_il);

-- Percorsi di comando rinominati (modello della 0488). Rilanciarla non cambia nulla.
UPDATE guild_config g
SET settings = jsonb_set(g.settings, '{policy_comandi_off}', (
    SELECT COALESCE(jsonb_agg(DISTINCT to_jsonb(COALESCE(m.nuovo, e.v))), '[]'::jsonb)
    FROM jsonb_array_elements_text(g.settings -> 'policy_comandi_off') AS e(v)
    LEFT JOIN (WITH m(vecchio, nuovo) AS (VALUES
        ('utility tag', 'tag usa'),
        ('admin-messaggi tag crea', 'admin-tag tag crea'),
        ('admin-messaggi tag modifica', 'admin-tag tag modifica'),
        ('admin-messaggi tag elimina', 'admin-tag tag elimina'),
        ('admin-messaggi tag elenco', 'admin-tag tag elenco'),
        ('admin-messaggi tag prefisso', 'admin-tag tag prefisso'),
        ('admin-messaggi risposte crea', 'admin-tag risposte crea'),
        ('admin-messaggi risposte elimina', 'admin-tag risposte elimina'),
        ('admin-messaggi risposte elenco', 'admin-tag risposte elenco')
    ) SELECT vecchio, nuovo FROM m) m ON m.vecchio = e.v))
WHERE jsonb_typeof(g.settings -> 'policy_comandi_off') = 'array';

UPDATE guild_config_history h
SET old_value = CASE WHEN h.old_value ~ '^\s*\[' THEN (
        SELECT COALESCE(jsonb_agg(DISTINCT to_jsonb(COALESCE(m.nuovo, e.v))), '[]'::jsonb)::text
        FROM jsonb_array_elements_text(h.old_value::jsonb) AS e(v)
        LEFT JOIN (WITH m(vecchio, nuovo) AS (VALUES
        ('utility tag', 'tag usa'),
        ('admin-messaggi tag crea', 'admin-tag tag crea'),
        ('admin-messaggi tag modifica', 'admin-tag tag modifica'),
        ('admin-messaggi tag elimina', 'admin-tag tag elimina'),
        ('admin-messaggi tag elenco', 'admin-tag tag elenco'),
        ('admin-messaggi tag prefisso', 'admin-tag tag prefisso'),
        ('admin-messaggi risposte crea', 'admin-tag risposte crea'),
        ('admin-messaggi risposte elimina', 'admin-tag risposte elimina'),
        ('admin-messaggi risposte elenco', 'admin-tag risposte elenco')
    ) SELECT vecchio, nuovo FROM m) m ON m.vecchio = e.v) ELSE h.old_value END,
    new_value = CASE WHEN h.new_value ~ '^\s*\[' THEN (
        SELECT COALESCE(jsonb_agg(DISTINCT to_jsonb(COALESCE(m.nuovo, e.v))), '[]'::jsonb)::text
        FROM jsonb_array_elements_text(h.new_value::jsonb) AS e(v)
        LEFT JOIN (WITH m(vecchio, nuovo) AS (VALUES
        ('utility tag', 'tag usa'),
        ('admin-messaggi tag crea', 'admin-tag tag crea'),
        ('admin-messaggi tag modifica', 'admin-tag tag modifica'),
        ('admin-messaggi tag elimina', 'admin-tag tag elimina'),
        ('admin-messaggi tag elenco', 'admin-tag tag elenco'),
        ('admin-messaggi tag prefisso', 'admin-tag tag prefisso'),
        ('admin-messaggi risposte crea', 'admin-tag risposte crea'),
        ('admin-messaggi risposte elimina', 'admin-tag risposte elimina'),
        ('admin-messaggi risposte elenco', 'admin-tag risposte elenco')
    ) SELECT vecchio, nuovo FROM m) m ON m.vecchio = e.v) ELSE h.new_value END
WHERE h.key_name = 'policy_comandi_off';

WITH m(vecchio, nuovo) AS (VALUES
        ('utility tag', 'tag usa'),
        ('admin-messaggi tag crea', 'admin-tag tag crea'),
        ('admin-messaggi tag modifica', 'admin-tag tag modifica'),
        ('admin-messaggi tag elimina', 'admin-tag tag elimina'),
        ('admin-messaggi tag elenco', 'admin-tag tag elenco'),
        ('admin-messaggi tag prefisso', 'admin-tag tag prefisso'),
        ('admin-messaggi risposte crea', 'admin-tag risposte crea'),
        ('admin-messaggi risposte elimina', 'admin-tag risposte elimina'),
        ('admin-messaggi risposte elenco', 'admin-tag risposte elenco')
)
UPDATE command_usage c
SET command_path = m.nuovo
FROM m
WHERE c.command_path = m.vecchio;
