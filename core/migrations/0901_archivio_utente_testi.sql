-- LOG-029 (D122): ai casi di sanzione si copiano, cifrati, i messaggi dell'utente degli ultimi 3 giorni.
-- Restano finché esiste il caso (stessa riga dell'archivio, quindi stessa cancellazione).
ALTER TABLE moderation_archivio_utente ADD COLUMN IF NOT EXISTS testi_cifrato TEXT;
ALTER TABLE moderation_archivio_utente ADD COLUMN IF NOT EXISTS testi_messaggi INTEGER NOT NULL DEFAULT 0;
