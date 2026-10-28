# Memoria di revisore-capo

## Aggiornata
28/10/2026 · ramo `feat/r10mod` (mute a tempo/hardmute/rientro 0270, caso registra, casi esterni, avvisi staff, SPEC §5.1–5.10 [x]): fatto anche il lavoro del cacciatore. Corretti 03c4116, a1b2092, a3587dd, 4ab5dfc, 9885eba. Esito APPROVATO con 2 basse aperte. Smoke da fare (regola owner: solo test dei file toccati).

## In corso
- `feat/r10mod`: 2 basse aperte (quaderno 28/10). Prima dell'unione: merge di main (conflitti solo in documenti e COMMAND_LIST*, poi rigenerare). Smoke unico a fine giro (lo lancia l orchestratore).
- `feat/r9nsfw`: 1 bassa (tetto promemoria letto-poi-scritto).
- `feat/r8web`: «IPv4 da solo = basso» da far confermare all'owner. `feat/r8uti`: 1 bassa (schede senza «vede il canale»). `feat/r8tkt`: 1 bassa (`_ruolo_secondo_ai`).
- `feat/r7mod`: aperti noti in SPEC/REGISTRO; `_shared.py:192` Mod non «il bot stesso» (bassa). `feat/r7liv`: 3 basse, sfondo per tutti da confermare. `feat/r6mus`: 1 bassa.
- Rami in attesa di riconsegna (righe nel quaderno): r4-tkt, r4-uti, r4-liv, r3-mus, r3-bak, giro-mod, giro-logt, #66, #67, #147, #76, #59/#117, #146, #134, #135/#136. `f7-quadro` APPROVATO, manca l'unione. Alla riconsegna: solo le righe aperte.
- Aperti bassi: r6ai per dev-ai; r6mod `/antiraid segnala` senza tetto.

## Fatto
- Letti per intero: giro-mod, r3-bak, r3-mus, r4-liv, r4-tkt, r4-uti, r6ai, r6mod, r6web, r6mus, r7bak, r7mod, r7liv, r8tkt, r8uti, r8web, r9mod, r9nsfw, r10mod.

## Cose imparate
- Controllare il contenuto di ogni commit, non il messaggio; testo all'utente che promette una funzione va confrontato col codice.
- Ambiente: `source` dello script env in ogni bash; mai riavviare postgres se lo dice la scheda; `python3 -m pytest -p no:cacheprovider`.
- Merge di main: conflitti nei documenti e in `comandi.en.json`; `COMMAND_LIST*.md` si rigenerano (`scripts/generate_command_list.py`, l'errore finale «Client not initialised» è innocuo). Comando nuovo senza elenco rigenerato = rilievo.
- Chiavi `SETTING_X` in `SETTINGS_SCHEMA` (solo owner: `CHIAVI_SOLO_PROPRIETARIO`); `test_config_import_validation.py`. Tabelle nuove in `core/data_registry.py`; metodi di repo senza chiamanti rompono `test_repository_callers.py`.
- Migrazioni tracciate per numero/nome: ordine fuori sequenza va bene, una modificata non si riapplica. Confrontare i numeri di tutti i rami (anche le D di DECISIONI, con `git show main:`).
- Mutazioni: su COPIA, script `python3 -I` in scratchpad con `str.replace` contato e ripristino; più mutazioni in un solo script. Test che si blocca: `asyncio.wait(..., timeout=)`.
- Comandi con più opzioni: tutti i controlli PRIMA di ogni salvataggio, o errore mostrato e metà salvata.
- Membro alla scadenza (scheduler): `trova_membro` (cache poi fetch), mai solo `get_member`.
- Azioni nuove che toccano un utente (anche solo un caso registrato): gerarchia + ruoli immuni (`check_can_moderate`, `azione_su_discord=False` se su Discord non si fa nulla).
- Azioni automatiche partite da un moderatore: tetto = ciò che lui può fare (D28, D29); in massa mai fuori dai tetti MOD-002.
- Ripristini (unlock, scadenze): un «no» salvato come «permesso di prima» lascia bloccato.
- Stato in memoria/cache: chi lo svuota, versione contro leggi-poi-set, cosa succede al riavvio. Task per chiave: uno solo, riferimento tenuto, fermati in `cog_unload`.
- Finti: `member.roles` vivo non prova un'istantanea vecchia; `fake_guild` ha `owner_id=555` e `get_member` None; `Thread.permissions_for` eredita; `create_autospec(discord.Thread)` per `isinstance`.
- `AllowedMentions(roles=...)` ha `everyone=True` di default. `monkeypatch.undo()` toglie il pool; `monkeypatch.setattr(asyncio, "sleep")` è globale. Tetti in memoria globali: azzerarli nella fixture.
- Bot secondario (D15): cercare OGNI azione della sua area ancora chiamata sul principale. App utente: `is_guild_integration()` falso = saltare le cose del server.

## Aperto
- Domande all'owner: SPEC 23.16 (sfondo solo colore), D18 limite ticket per utente, conferma primo DM ModMail, D27, IPv4 = basso (NF-21), D29.
