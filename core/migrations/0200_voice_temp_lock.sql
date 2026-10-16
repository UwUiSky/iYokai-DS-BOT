-- #144 (residuo): /voice lock ricorda nel database il valore di «Connetti»
-- che @everyone aveva prima. Così /voice unlock lo ripristina anche dopo
-- un riavvio del bot. bloccato = false: nessun lock attivo.
ALTER TABLE voice_temp_channels ADD COLUMN IF NOT EXISTS bloccato BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE voice_temp_channels ADD COLUMN IF NOT EXISTS connect_prima BOOLEAN;
