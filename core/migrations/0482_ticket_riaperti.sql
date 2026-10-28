-- 23.17 (D51): quante volte un ticket è stato riaperto dopo la chiusura (carico dello staff).
ALTER TABLE tickets ADD COLUMN IF NOT EXISTS riaperto_volte INTEGER NOT NULL DEFAULT 0;
