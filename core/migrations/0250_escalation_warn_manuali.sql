-- M 1.10 (#57): la scala di escalation conta anche i warn dati a mano.
ALTER TABLE automod_escalation_config ADD COLUMN IF NOT EXISTS conta_warn_manuali BOOLEAN NOT NULL DEFAULT FALSE;
