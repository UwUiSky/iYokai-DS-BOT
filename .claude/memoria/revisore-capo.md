# Memoria di revisore-capo

## Aggiornata
14/10/2026 · ramo `feat/r6mod` (e420745) #115/#116/#117/#118: corretti dal revisore i 4 plausibili del cacciatore, smoke lanciato

## In corso
- `feat/r6mod`: su richiesta dell'orchestratore il revisore ha corretto (e420745): AMD-019 embed via modifica e solo filtri link, solo-media con sticker/inoltri, captcha 3 errori in 24 h, gerarchia massa con `fetch_member`. Aperto basso: `/antiraid segnala` senza tetto (DM all'owner del bot). Esito smoke nel rapporto.
- `feat/r4-tkt` (674e3b0): DA SISTEMARE (23 righe nel quaderno del ramo; alte: `_menu_aperti` ModMail, regex del log lente, risposte standard con dati personali). Alla riconsegna controllare solo quelle.
- `feat/r4-uti` (66055f9): DA SISTEMARE (21 righe; `/gestione` oltre 8000 all'unione con liv+tkt).
- `feat/r4-liv` (40e6b5e): 9 righe corrette dal dev, smoke 886 verde: da riapprovare.
- In attesa (vedi quaderno di ciascuno): `feat/r3-mus` 8, `feat/r3-bak` 8, `giro-mod` 12, `giro-logt` 11, #66 12, #67 8, #147 6, #76 5+7, #59/#117 2, #146, #134, #135/#136 (`remove_member` deadlock). `feat/f7-quadro` APPROVATO, manca l'unione.

## Fatto
- F1 del 05/10 unito (`7722b71`, `3758f2a`, `9db9e8a`). Letti per intero: giro-mod, r3-bak, r3-mus, r4-liv, r4-tkt, r4-uti, r6mod.

## Cose imparate
- Cambio "giusto" può peggiorare un'altra area: controllare il contenuto di ogni commit. Testo all'utente che promette una funzione va confrontato con ciò che il codice fa.
- Ambiente: `source /tmp/claude-0/env_<ramo>.sh` in ogni bash (DB per processo); `python3 -m pytest`; mai `cd` dentro lo script env.
- Funzioni private `db._…` usate da un cog = manca una funzione pubblica. Più blocchi: controllare TUTTI i punti che bloccano le stesse tabelle.
- Setting nuove: `SETTINGS_SCHEMA` (config_history.py) + `test_config_import_validation.py`; tabelle nuove in `core/data_registry.py`; metodi di repo senza chiamanti rompono `test_repository_callers.py`.
- Mutazioni: su COPIA del file (cp in scratchpad, poi ripristino), mai `git checkout -- file` con lavoro non committato; `str.replace(..,1)` contato; `WHERE guild_id = $1` → `$1::bigint IS NOT NULL`.
- Doppio clic / blocchi: `asyncio.gather` con `tests/support/concorrenza.apri_connessioni`; un blocco per chiave A non protegge un vincolo su chiave B.
- Suite completa >10 min: mai. Smoke in background con `nohup` e poll ≤119 s; `pkill -f` col testo del comando uccide la propria shell.
- Stato in memoria (dizionari, tetti orari): chiedersi chi lo ripulisce e cosa succede al riavvio; scriverlo in VERIFICA_LIVE se è un limite accettato.
- Regex di admin: `re` senza timeout; schemi con `*` e `?` costano centinaia di ms.
- `AllowedMentions(roles=...)` ha `everyone=True` di default: passare `everyone=False`. `monkeypatch.undo()` toglie anche il pool del DB.
- Embed delle anteprime link arrivano con `on_message_edit` a testo invariato; il loro testo non è dell'utente (niente caps/lunghezza).
- Fake guild MagicMock: `fetch_member` non è awaitable di base, va impostato nel test (NotFound di default).
- Test che leggono export: struttura `dati["tabelle"][nome]["righe"]`; asserzioni vuote passano sempre.

## Aperto
- Domande all'owner: SPEC 23.16 (sfondo solo colore), D18 limite ticket per utente, conferma del primo DM ModMail.
