-- 19.9 (SEC-16): i token dei webhook ricevuti si salvano come impronta SHA-256.
-- I token già esistenti diventano impronta e continuano a funzionare; il testo in chiaro sparisce.
ALTER TABLE custom_webhooks ADD COLUMN IF NOT EXISTS token_hash TEXT;
ALTER TABLE custom_webhooks ALTER COLUMN token DROP NOT NULL;
UPDATE custom_webhooks
   SET token_hash = encode(sha256(convert_to(token, 'UTF8')), 'hex')
 WHERE token_hash IS NULL AND token IS NOT NULL;
UPDATE custom_webhooks SET token = NULL WHERE token IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_custom_webhooks_token_hash ON custom_webhooks (token_hash);
