-- Catalogo #128 (UTL-070): innesco «canale scorciatoia»: ogni messaggio scritto nel canale fa partire il tag, con il testo
-- come argomento.
ALTER TABLE tag_inneschi DROP CONSTRAINT IF EXISTS tag_inneschi_tipo_check;
ALTER TABLE tag_inneschi ADD CONSTRAINT tag_inneschi_tipo_check
    CHECK (tipo IN ('reazione', 'intervallo', 'orario', 'bottone', 'ruolo_dato', 'ruolo_tolto', 'canale_testo'));
