-- D69 B13: quante volte un membro è uscito dal server (per il segnaposto {rientri} del benvenuto).
ALTER TABLE invite_joins ADD COLUMN IF NOT EXISTS usciti INT NOT NULL DEFAULT 0;
