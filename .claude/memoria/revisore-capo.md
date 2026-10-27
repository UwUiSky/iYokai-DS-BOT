# Memoria di revisore-capo

## Aggiornata
27/10/2026 · ramo `feat/r10amod` (#58/#116 AutoMod: parole con modo, inviti permessi/propri, violazioni, escalation che cresce; 0280–0282). Fatto anche il lavoro del cacciatore. Corretti: eccezioni proprie tenute se `guild.invites()` fallisce + invito personalizzato + indice violazioni (7ac974a); fixture con monkeypatch e COMMAND_LIST (95f0902); documenti nel commit dopo. APPROVATO.

## In corso
- `feat/r10amod`: 3 basse aperte nel quaderno (oltre 8 inviti propri, attesa 3 s non annullata, test sic042 dipendente dall'ordine). Migrazione 0282 nuova: suite completa a scelta dell'orchestratore.
- `feat/r9nsfw`: 1 bassa (tetto promemoria letto-poi-scritto). `feat/r9mod`: D29 da segnalare all'owner.
- `feat/r8web`: «IPv4 da solo = basso» da far confermare. `feat/r8uti`: 1 bassa. `feat/r8tkt`: 1 bassa accettata.
- `feat/r7mod`: aperti noti in SPEC/REGISTRO; `_shared.py:192` Mod non «il bot stesso» (bassa). `feat/r7liv`: 3 basse. `feat/r6mus`: 1 bassa.
- Rami in attesa di riconsegna (righe nel quaderno): r4-tkt, r4-uti, r4-liv, r3-mus, r3-bak, giro-mod, giro-logt, #66, #67, #147, #76, #59/#117, #146, #134, #135/#136. `f7-quadro` APPROVATO, manca l'unione.
- Aperti bassi: r6ai per dev-ai; r6mod `/antiraid segnala` senza tetto.

## Fatto
- Letti per intero: giro-mod, r3-bak, r3-mus, r4-liv, r4-tkt, r4-uti, r6ai, r6mod, r6web, r6mus, r7bak, r7mod, r7liv, r8tkt, r8uti, r8web, r9mod, r9nsfw, r10amod.

## Cose imparate
- Controllare il contenuto di ogni commit, non il messaggio; testo all'utente che promette una funzione va confrontato col codice. REGISTRO/SPEC: confrontare con ciò che il ramo fa davvero.
- Ambiente: script env in ogni bash; mai riavviare postgres. Lo smoke dello sviluppatore usa lo STESSO database: per i miei test creare un database mio (`CREATE DATABASE iyokai_wrev<ramo>`), o i test si rompono a vicenda.
- Merge di main: conflitti nei documenti e in `comandi.en.json`; `COMMAND_LIST*.md` si rigenerano con `scripts/generate_command_list.py` (l'errore finale del client è innocuo).
- Funzioni `db._…` usate da un cog = manca una funzione pubblica. Chiavi `SETTING_X` in `SETTINGS_SCHEMA`; tabelle nuove in `core/data_registry.py`; metodi senza chiamanti rompono `test_repository_callers.py`.
- Migrazioni tracciate per NOME; numeri da confrontare su tutti i rami (`git ls-tree <ramo> core/migrations/`). Query nuove su tabelle di log: indice.
- Mutazioni: su COPIA, script `python3 -I` con `str.replace` contato, poi ripristino. Test che si blocca: `asyncio.wait(..., timeout=)`.
- Leggi-poi-scrivi e doppio clic: `asyncio.gather` con `tests/support/concorrenza.apri_connessioni`. Test instabili: due letture dello stesso stato.
- Task programmati per chiave: uno solo per chiave, fermati in `cog_unload`. Stato in memoria: chi lo svuota, riavvio.
- Finti: `member.roles` vivo; `Permissions.all()` per admin; `Pool.fetchrow` sola lettura (finto sul `_pool_provider`); `create_autospec(Guild)` dà MagicMock per gli attributi: controllare con `isinstance`.
- `AllowedMentions(roles=...)` ha `everyone=True`. `monkeypatch.setattr(asyncio, "sleep")` è globale.
- Bot secondario (D15): ogni azione della sua area. Azioni automatiche partite da un moderatore: tetto = ciò che lui può fare (D28, D29).
- `locales/comandi.en.json` "nomi" è per SEGMENTO, globale; menu del tasto destro in sezione `menu`.
- AutoMod nativo: un errore nel leggere un dato esterno (inviti) non deve svuotare le eccezioni: tenere l'ultimo sync. Vanity non è in `guild.invites()`.
- App utente: `is_guild_integration()` falso = server senza l'app; saltare politica, moduli, quote.

## Aperto
- Domande all'owner: SPEC 23.16 (sfondo solo colore), D18 limite ticket per utente, conferma primo DM ModMail, D27, IPv4 = basso (NF-21), D29.
