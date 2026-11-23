-- BKP-039 (D113, #118): pagina di consenso per il rientro dopo un ripristino, su /join/<nome>.
-- Il server la accende (join_attiva), sceglie un nome breve unico (join_slug) e due colori (#rrggbb). Senza nome si usa l'ID.
ALTER TABLE web_panel_pubblico ADD COLUMN IF NOT EXISTS join_attiva  BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE web_panel_pubblico ADD COLUMN IF NOT EXISTS join_slug    TEXT;
ALTER TABLE web_panel_pubblico ADD COLUMN IF NOT EXISTS join_accento TEXT;
ALTER TABLE web_panel_pubblico ADD COLUMN IF NOT EXISTS join_sfondo  TEXT;
ALTER TABLE web_panel_pubblico DROP CONSTRAINT IF EXISTS web_panel_pubblico_join_slug_forma;
ALTER TABLE web_panel_pubblico ADD CONSTRAINT web_panel_pubblico_join_slug_forma
    CHECK (join_slug IS NULL OR join_slug ~ '^[a-z0-9]([a-z0-9-]{1,30})[a-z0-9]$');
ALTER TABLE web_panel_pubblico DROP CONSTRAINT IF EXISTS web_panel_pubblico_join_colori_forma;
ALTER TABLE web_panel_pubblico ADD CONSTRAINT web_panel_pubblico_join_colori_forma
    CHECK ((join_accento IS NULL OR join_accento ~ '^#[0-9a-f]{6}$') AND (join_sfondo IS NULL OR join_sfondo ~ '^#[0-9a-f]{6}$'));
CREATE UNIQUE INDEX IF NOT EXISTS web_panel_pubblico_join_slug ON web_panel_pubblico (join_slug) WHERE join_slug IS NOT NULL;
