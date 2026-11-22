-- BKP-008, #121: copie automatiche della struttura a intervalli, con più copie tenute.
CREATE TABLE IF NOT EXISTS backup_automatici (
    guild_id    BIGINT PRIMARY KEY,
    ore         INTEGER NOT NULL CHECK (ore BETWEEN 4 AND 168),
    copie       INTEGER NOT NULL CHECK (copie BETWEEN 1 AND 8),
    created_by  BIGINT NOT NULL,
    ultimo      TIMESTAMPTZ,
    creato_il   TIMESTAMPTZ NOT NULL DEFAULT now()
);
