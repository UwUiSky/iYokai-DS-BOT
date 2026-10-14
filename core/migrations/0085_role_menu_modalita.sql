-- NF-14 (#85, M 10.8): comportamento dei menu di ruoli (unique, verify, drop, reversed,
-- binding, temp, lock) e ruoli ammessi o esclusi. role_menus nasce nel codice di base.
ALTER TABLE role_menus ADD COLUMN IF NOT EXISTS behavior          TEXT NOT NULL DEFAULT 'normal';
ALTER TABLE role_menus ADD COLUMN IF NOT EXISTS temp_seconds      INTEGER;
ALTER TABLE role_menus ADD COLUMN IF NOT EXISTS allowed_role_ids  BIGINT[] NOT NULL DEFAULT '{}';
ALTER TABLE role_menus ADD COLUMN IF NOT EXISTS excluded_role_ids BIGINT[] NOT NULL DEFAULT '{}';
