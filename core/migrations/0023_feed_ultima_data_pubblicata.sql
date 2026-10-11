-- #67 (11.5): data dell'ultimo elemento pubblicato di un feed. Se l'ultimo
-- elemento visto sparisce dal feed, si pubblicano solo quelli piu' recenti
-- di questa data invece di ripubblicare tutto. Nessun dato personale.
ALTER TABLE feed_subscriptions
    ADD COLUMN IF NOT EXISTS last_seen_published TIMESTAMPTZ;
