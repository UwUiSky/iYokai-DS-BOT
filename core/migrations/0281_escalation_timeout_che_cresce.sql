-- AMD-070 (#116): il timeout oltre l'ultimo gradino cresce a ogni ricaduta.
ALTER TABLE automod_escalation_config ADD COLUMN IF NOT EXISTS moltiplicatore REAL NOT NULL DEFAULT 1;
ALTER TABLE automod_escalation_config ADD COLUMN IF NOT EXISTS tetto_strike INTEGER NOT NULL DEFAULT 5;
