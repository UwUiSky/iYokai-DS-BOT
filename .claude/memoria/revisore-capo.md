# Memoria di revisore-capo

## Aggiornata
14/10/2026 · ramo `feat/r6ai` (9f323ca) #95 motore AI: APPROVATO dopo correzioni dirette (su richiesta dell'orchestratore); 1 riga bassa aperta nel quaderno

## In corso
- Nessuna voce in corso su r6ai. Smoke `--base main`: 972 verdi.
- Rami in attesa di riconsegna (dettagli nel quaderno di ciascuno): `feat/r4-uti` 21 righe, `feat/r4-tkt` 23, `feat/r4-liv` (da riapprovare, smoke 886), `feat/r3-mus` 8, `feat/r3-bak` 8, `giro-mod` 12, `giro-logt` 11, #66 12, #67 8, #147 6, #76 5+7, #59/#117 2, #146, #134, #135/#136 (`remove_member`). `f7-quadro` APPROVATO, manca l'unione.

## Fatto
- F1 del 05/10 unito. Letti per intero: giro-mod, r3-bak, r3-mus, r4-liv, r4-tkt, r6ai.
- r6ai 9f323ca: quote/tetto atomici (prenota/conferma/annulla), `menziona_percorsi`, premium nella porta unica, thread privati in `spiega`, ingrandimento via safe_image.

## Cose imparate
- Cambio "giusto" può peggiorare un'altra area: controllare il contenuto di ogni commit, non il messaggio. Testo all'utente che promette una funzione va confrontato con ciò che il codice fa.
- DB per processo (`iyokai_wrevisore2`), `python3 -m pytest`, `postgres:testpass@127.0.0.1`. Senza `DATABASE_URL` i test usano `iyokai_test` (condiviso, `clean_db` lo svuota): esportarlo SEMPRE, anche per prove al volo. Mai fare `cd` dentro lo script env: i file finiscono nel ramo.
- Funzioni private `db._…` usate da un cog = manca una funzione pubblica. Più blocchi: controllare TUTTI i punti che bloccano le stesse tabelle.
- Chiavi `SETTING_X`/`KEY_*` nuove vanno in `SETTINGS_SCHEMA` (config_history.py); lo smoke non sceglie quel test se non si tocca il file. Tabelle nuove: voce in `core/data_registry.py`.
- Stato su più comandi: provare la sequenza A->B->C con un test temporaneo. Task che riprovano per sempre bloccano chi fa `gather`: provare con gestore vero.
- Mutazioni: `WHERE guild_id = $1` -> `$1::bigint IS NOT NULL` (togliere il parametro dà InterfaceError, non conta come uccisa); contare le occorrenze prima di `replace`; lavorare su una COPIA e fare `diff -rq` a fine giro.
- `Permissions(view_channel=False)` ha anche manage_messages=False: fissare l'altro permesso a True.
- Doppio clic / blocchi: serve `asyncio.gather` con `tests/support/concorrenza.apri_connessioni`; un blocco per chiave A non protegge un vincolo su chiave B. Un blocco advisory tolto che non fa fallire nessun test = test mancante (provare con 30 chiamate insieme).
- Prezzo/importo: se il DB decide il valore, anche messaggio e rimborso devono usare QUEL valore (o rifiutare se diverso dal letto).
- Mutanti equivalenti da riconoscere: tetto già garantito a monte (`[:256]` con premio max 200; elenco 25x76 < 2000).
- Suite completa >10 min: non lanciarla. Voci già a posto sul base: `git show base:file`. `pkill -f` col testo del comando uccide la propria shell.
- Prove #76: GRUPPI globale condiviso tra test; il lookbehind dei riferimenti esclude i backtick; chiavi `KEY_*` sfuggono al test invariante.
- Migrazioni: confrontare i numeri di TUTTI i rami (`git diff main...ramo --name-only -- core/migrations`) + prova due volte su DB con i dati di main (`git archive main`).

- Thread privati: `Thread.permissions_for` eredita dal padre, non basta per «pubblico». Finti che condividono `member.roles` vivo non provano un'istantanea vecchia dell'interazione: servono copie congelate.
- Harness mutazioni: script con `str.replace` contato + `git checkout` finale; lanciare con timeout 595000 sul tool (non `pkill -f` col nome dello script: uccide la propria shell).
- Con lavoro non committato NON ripristinare le mutazioni con `git checkout -- file` (perde le correzioni): fare `git stash` + `stash apply` prima, o copia del file.
- Gare tra persone diverse: blocco advisory in transazione + prenotazione nella tabella dei conti; per far fallire il test senza blocco servono `apri_connessioni` E una lettura rallentata (monkeypatch del `_uso`), altrimenti le richieste si sfalsano da sole.
- Moduli premium: i listener e i comandi fuori gruppo non passano da `requires_module`: il controllo va nella porta unica.

## Aperto
- Domanda all'owner: SPEC 23.16 (sfondo solo colore) accettato o `[~]`?
- r6ai: riga bassa (ticket staff, pacchetto, riassumi doppio, vietate) da passare al dev-ai.
14/10/2026 · ramo `feat/r6web` (#91 pannello web): lasciato di sicurezza corretto su ordine dell'orchestratore (D28, proxy fidato, cache membri), commit f1829fc

## In corso
- `feat/r6web`: corretti D28 (ruolo admin solo con «Amministratore», punto unico `errore_ruolo_admin`), `WEB_PANEL_TRUSTED_PROXY`, cache `fetch_member` 30 s, guida README. 7 mutazioni tutte uccise. Esito smoke nel rapporto.
- Rami in attesa di riconsegna (righe nel quaderno di ciascun ramo): `feat/r4-tkt` 23, `feat/r4-uti` 21, `feat/r4-liv` 9 (corrette, da riapprovare), `feat/r3-mus` 8, `feat/r3-bak` 8, `giro-mod` 12, `giro-logt` 11, #66 12, #67 8, #147 6, #76 5+7, #59/#117 2, #146, #134, #135/#136 (`remove_member` deadlock). `f7-quadro`: APPROVATO, manca l'unione. Alla riconsegna: controllare solo le righe aperte.

## Fatto
- F1 del 05/10 unito (`7722b71`, `3758f2a`, `9db9e8a`). Letti per intero: giro-mod, r3-bak, r3-mus, r4-liv, r4-tkt, r4-uti, r6web.

## Cose imparate
- Controllare il contenuto di ogni commit, non il messaggio. Testo all'utente che promette una funzione va confrontato col codice.
- DB per processo (`iyokai_wrevisore_<ramo>`), `python3 -m pytest`; esportare SEMPRE `DATABASE_URL` (senza: `iyokai_test` condiviso). Mai `cd` dentro lo script env.
- Funzioni private `db._…` usate da un cog = manca una funzione pubblica. Più blocchi: controllare TUTTI i punti sulle stesse tabelle.
- Chiavi `SETTING_X`/`KEY_*` nuove in `SETTINGS_SCHEMA`; tabelle nuove in `core/data_registry.py`; migrazioni: confrontare i numeri di tutti i rami + prova due volte su DB con i dati di main.
- Mutazioni: script con `str.replace` contato, su copia + confronto finale; lanciarlo con `python3 -I` (nello scratchpad c'è un `locale.py` che rompe gli script lanciati da lì). `WHERE guild_id = $1` -> `$1::bigint IS NOT NULL`.
- `Permissions(administrator=True)` finto NON ha `manage_guild`: il vero `Member.guild_permissions` sì (tutti). Nei test usare `Permissions.all()`.
- Finti con `member.roles` vivo non provano un'istantanea vecchia: servono copie congelate. `Thread.permissions_for` eredita dal padre.
- Doppio clic: `asyncio.gather` con `tests/support/concorrenza.apri_connessioni`; blocco advisory tolto senza test rosso = test mancante.
- Prezzo/importo: se il DB decide il valore, messaggio e rimborso usano QUEL valore.
- Mutanti equivalenti: tetto già garantito a monte.
- Suite completa >10 min: non lanciarla. `pkill -f` col testo del comando uccide la propria shell.
- Con lavoro non committato NON ripristinare con `git checkout -- file`: copia del file o stash.
- Ruoli che aprono un livello più alto (admin -> SECURITY): chi li sceglie deve avere il permesso del livello più alto (D28).

## Aperto
- Domanda all'owner: SPEC 23.16 (sfondo solo colore) accettato o `[~]`? D27 (pannello nel processo del bot) da confermare.
