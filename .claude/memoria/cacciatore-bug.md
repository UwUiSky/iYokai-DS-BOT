# Memoria di cacciatore-bug

## Aggiornata
28/10/2026 · `feat/r10inviti` (giro fatto dal revisore): 5 fix in 8b9426b, righe in `rapporti/bug.md`.
21/10/2026 · ultimi giri: `feat/r8tkt` (opzioni ticket #120, AI #139; 6 fix 92633fa…f8c87c8, i 4 lasciati li ha chiusi il revisore), `feat/r8web` (6 fix ec769c2…6de5e0f), `feat/r8uti` (c2af58d, 3d722cc, 416859f).
16/10/2026 · r7mod, r7bak (1172556, b70b41f), r7liv (635507f). 14/10 r6ai (9516f7c), r6web, r6mod. 13/10 r4-tkt/uti/liv.
21/10/2026 · ultimo giro: `feat/r9nsfw` (bot NSFW, App utente), 5 fix: 644985d, a5dc0b2, c93a382, b4a0667, 9aaf9dd.
22/10/2026 · ultimo giro: `feat/r9mod` (ripiego anti-nuke, warn→scala, /mod opzioni, lock a tempo, spamtrap punizione), fix d2d077a, 90ed830.
21/10/2026 · ultimo giro: `feat/r8web` (verifica web NF-21, #148, marchio, aspetto, «I miei dati»), 6 fix: ec769c2, 0e8943c, 87f72f9, 951cf86, db91e8c, 6de5e0f.
16/10/2026 · r7mod, r7bak, r7liv (fix in `rapporti/bug.md`).
28/10/2026 · `feat/r10logt` (log, ticket chiusi in due passi, vocali): 5 difetti, corretti dal revisore (031a2d3, a8866f8, ea2f070). Righe in `rapporti/bug.md`.

## In corso
- Niente a metà.

## Fatto
- Giri 28/09–16/10 (BUG-19…34, SEC-18…22, F1, giro-core, r3, r4-*, r6*, r7*): dettagli in `rapporti/bug.md`.
- 21–22/10: r8tkt, r8web, r8uti, r9nsfw, r9mod (fix elencati in `rapporti/bug.md`).
- 28/10 r10logt: aggiunti che leggono il ticket chiuso, Elimina su riaperto, eliminazione vecchia dopo riapertura, log ignora che nasconde ruoli/timeout/permessi, generatore privato copiato reso pubblico.

## Cose imparate
- Due client (Mod/principale): ogni oggetto in cache porta il SUO client; `http.*` via Mod salta i casi speciali di discord.py.
- Stato solo in memoria: chi lo svuota (evento spento, NF-04, riavvio). Cache «leggi, poi set» con await in mezzo: serve una versione.
- Difetti frequenti: leggi-poi-scrivi su saldi/contatori/tetti; risposte oltre i limiti; azioni fallite riportate come riuscite.
- Azioni fatte DAL bot non le vede l'anti-nuke: tetto proprio. Lavori nello scheduler legati a uno stato (ingresso, ticket chiuso): cancellarli quando lo stato torna indietro (`scheduler.cancel_for_channel`).
- Test di corsa: `tests/support/concorrenza.apri_connessioni`, provati togliendo il fix. `AsyncMock(side_effect=lambda: asyncio.sleep())` NON aspetta. `monkeypatch.setattr(asyncio, "sleep")` è globale.
- `Thread.permissions_for` = permessi del padre; thread archiviati non in `get_thread`. Contenuto citato/copiato: chi lo RICEVE.
- «Nascondi il canale a X»: guardare TUTTE le sovrascritture (utenti e ruoli aggiunti), non solo X. Bottoni persistenti rimasti dopo un cambio di stato: ricontrollare lo stato nel callback.
- Filtri «ignora» estesi: non devono mai nascondere eventi di sicurezza (ruoli, timeout, permessi, cancellazioni) — D34.
- Copia di permessi da un canale modello: unire, non sostituire, la sovrascrittura di @everyone.
- Regole con condizioni: valutarle in ordine; «ridai se tolto» senza tetto = ping-pong. Self-service: ricontrollare i permessi alla presa.
- Ordine blocchi: due cicli in parallelo, righe in ordine inverso. Migrazioni: confrontare i numeri con main e gli altri rami.
- Ogni tabella nuova: `tests/test_data_registry.py`; nell'export guardare le colonne di TERZI. Query nuove su event_log: serve l'indice (0001 ne aveva tolti).
- Regex degli admin con timeout; modelli str.format senza spec/conversioni. Ogni `on_message` con `guild is None` vede lo STESSO DM.
- Web: `no-referrer` → `Origin: null`; `del_cookie` senza `secure=` non cancella `__Host-`; aiohttp ≥3.12 multipart limita ogni parte; `isdigit()` accetta «²»; dietro proxy tutti hanno lo stesso IP.
- Filtri di parole: NFKD non basta; App utente fuori server = DM. Ambiente: DB condiviso tra worktree; permessi veri con `discord.Guild/Member(data=..., state=ConnectionState(...))`.

## Aperto
- r10logt: `/log cerca ruolo` non trova ruoli dati/tolti (solo nei details); riapertura con tetto letto-poi-scritto (bassa).
- r4-tkt: rilievi senza fix in `rapporti/bug.md` (13/10). Giro mod: stato salvato PRIMA dell'azione irreversibile.
- r8tkt plausibile: prompt injection su `_ruolo_secondo_ai`. r8web plausibili: limite_accesso condiviso, CGNAT, `token_di_sistema` senza Mod, revoca OAuth solo locale.
