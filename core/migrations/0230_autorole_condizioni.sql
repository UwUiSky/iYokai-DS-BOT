-- Catalogo #123 (RUO-034, 035, 036): condizioni sui ruoli automatici.
-- richiesti: il ruolo si dà solo a chi ha almeno uno di questi ruoli;
-- esclusi: non si dà a chi ne ha uno; ridai: se qualcuno lo toglie, torna.
ALTER TABLE autorole_rules ADD COLUMN IF NOT EXISTS required_role_ids BIGINT[] NOT NULL DEFAULT '{}';
ALTER TABLE autorole_rules ADD COLUMN IF NOT EXISTS excluded_role_ids BIGINT[] NOT NULL DEFAULT '{}';
ALTER TABLE autorole_rules ADD COLUMN IF NOT EXISTS reapply BOOLEAN NOT NULL DEFAULT FALSE;
