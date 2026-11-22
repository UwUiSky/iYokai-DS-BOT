-- AI-017, #132: funzioni AI spente una per una (l'AI del server resta spenta finché non si accende).
ALTER TABLE ai_config ADD COLUMN IF NOT EXISTS funzioni_spente TEXT[] NOT NULL DEFAULT '{}';
