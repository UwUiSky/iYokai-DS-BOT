-- FUN-017 (D122): le foto delle auto passano da un controllo automatico dei contenuti per adulti (snodo AI).
-- NULL = non ancora controllata (le foto già salvate si ricontrollano alla prossima visualizzazione).
ALTER TABLE fun_auto_foto ADD COLUMN IF NOT EXISTS controllata_il TIMESTAMPTZ;
