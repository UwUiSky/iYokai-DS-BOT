-- F7 (#76): impronta dell'albero dei comandi già sincronizzato con Discord,
-- per ambito ('global' oppure 'guild:<id>'). Il bot sincronizza solo se
-- l'impronta cambia. Nessun dato personale.
CREATE TABLE IF NOT EXISTS command_sync_state (
    scope      TEXT PRIMARY KEY,
    tree_hash  TEXT NOT NULL,
    synced_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
