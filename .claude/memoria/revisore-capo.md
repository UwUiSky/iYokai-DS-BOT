# Memoria di revisore-capo

## Aggiornata
14/10/2026 · ramo `feat/r6web` (#91 pannello web): lasciato di sicurezza corretto su ordine dell'orchestratore (D27, proxy fidato, cache membri), commit f1829fc

## In corso
- `feat/r6web`: corretti D27 (ruolo admin solo con «Amministratore», punto unico `errore_ruolo_admin`), `WEB_PANEL_TRUSTED_PROXY`, cache `fetch_member` 30 s, guida README. 7 mutazioni tutte uccise. Esito smoke nel rapporto.
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
- Ruoli che aprono un livello più alto (admin -> SECURITY): chi li sceglie deve avere il permesso del livello più alto (D27).

## Aperto
- Domanda all'owner: SPEC 23.16 (sfondo solo colore) accettato o `[~]`? D26 (pannello nel processo del bot) da confermare.
