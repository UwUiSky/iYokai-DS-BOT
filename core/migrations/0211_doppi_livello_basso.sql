-- NF-21 (#92): livello «basso» per i doppi con lo stesso IPv4 e browser diverso
-- (CGNAT, scuole, famiglie: core/alt_detection_logic.valuta_doppi).
ALTER TABLE verify_doppi DROP CONSTRAINT IF EXISTS verify_doppi_livello_check;
ALTER TABLE verify_doppi ADD CONSTRAINT verify_doppi_livello_check CHECK (livello IN ('alto', 'medio', 'basso'));
