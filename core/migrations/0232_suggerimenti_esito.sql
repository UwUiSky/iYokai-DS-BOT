-- Catalogo #128 (UTL-135, 136): motivo scritto dallo staff nella decisione;
-- stati in più "considering" (in valutazione) e "implemented" (realizzato).
ALTER TABLE suggestions ADD COLUMN IF NOT EXISTS decision_reason TEXT;
