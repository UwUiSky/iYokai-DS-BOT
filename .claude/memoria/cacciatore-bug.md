# Memoria di cacciatore-bug

## Aggiornata
21/10/2026 · ultimi giri: `feat/r8tkt` (opzioni ticket #120, AI #139; 6 fix 92633fa…f8c87c8, i 4 lasciati li ha chiusi il revisore), `feat/r8web` (6 fix ec769c2…6de5e0f), `feat/r8uti` (c2af58d, 3d722cc, 416859f).
16/10/2026 · r7mod, r7bak (1172556, b70b41f), r7liv (635507f). 14/10 r6ai (9516f7c), r6web, r6mod. 13/10 r4-tkt/uti/liv.

## In corso
- Niente a metà.

## Fatto
- Giri 28/09–14/10 (BUG-19…34, SEC-18…22, F1, giro-core, r3, r4-*, r6*, r7*): dettagli in `rapporti/bug.md`. Prove in scratchpad/cb*.
- r8tkt: link citato (titolare + thread privati), ruoli durante = self-service, AI scelta conta_utente, richiesta chiusura annullata se l'utente scrive, tetto pannello sotto blocco, osservatori non chiudono.
- r8web: caricamento 8 KB, log /verifica, IP interni = doppi, export verify_doppi, avvisi ripetuti, cifre Unicode.
- r8uti: ruoli a scelta ricontrollo permessi, lock massa, condizioni autoruoli in ordine + tetto ridai, tetto promemoria/nel canale.

## Cose imparate
- Due client (Mod/principale): ogni oggetto in cache porta il SUO client; cache separate per bot; `http.*` via Mod salta i casi speciali di discord.py.
- Stato solo in memoria: chi lo svuota (evento spento, NF-04, riavvio). Cache «leggi, poi set» con await in mezzo: serve una versione.
- Difetti frequenti: leggi-poi-scrivi su saldi/contatori/tetti; risposte oltre i limiti; azioni fallite riportate come riuscite.
- Azioni fatte DAL bot non le vede l'anti-nuke: serve un tetto proprio. Lavori nello scheduler legati all'ingresso: cancellarli al rientro.
- Test di corsa: `tests/support/concorrenza.apri_connessioni`, sempre provati togliendo il fix (copia in scratchpad). `AsyncMock(side_effect=lambda: asyncio.sleep())` NON aspetta. `monkeypatch.setattr(modulo.asyncio, "sleep", …)` cambia sleep per TUTTI.
- discord.py `Thread.permissions_for` = permessi del padre; thread archiviati non stanno in `get_thread`. Contenuto citato/copiato: controllare chi lo RICEVE.
- AI: lavoro automatico che conta sulla persona = aggirabile; `conta_utente=False` su messaggio dell'utente = quota del server svuotabile; niente cache per somiglianza.
- Regole con condizioni: valutarle in ordine; «ridai se tolto» senza tetto = ping-pong. Self-service: ricontrollare i permessi alla presa.
- Ordine blocchi: due cicli in parallelo, righe in ordine inverso. `schema_migrations` è per NUMERO: confrontare con gli altri rami.
- Ogni tabella nuova: `tests/test_data_registry.py`; nell'export guardare le colonne di TERZI.
- Regex degli admin: `a?`xN+`a`xN, `.*.*x$` con timeout. Modelli str.format: vietare spec/conversioni.
- Ogni `on_message` con `guild is None` vede lo STESSO DM.
- Ambiente: DB condiviso tra worktree (`pgrep pytest`); prove in `tests/test_tmp_*.py` poi in scratchpad; permessi veri con `discord.Guild/Member(data=..., state=ConnectionState(...))`.
- Sincronie/caricamenti: ruoli per NOME = escalation; mai permessi pericolosi a @everyone; inviti/link creati dal bot: permesso di chi chiede.
- Web: `no-referrer` → `Origin: null`; `del_cookie` senza `secure=` non cancella `__Host-`; aiohttp ≥3.12 multipart limita ogni parte; access log redatto; `isdigit()` accetta «²»; dietro proxy tutti hanno lo stesso IP.

## Aperto
- r4-tkt: rilievi senza fix in `rapporti/bug.md` (13/10).
- Giro mod: lo stato si salva PRIMA dell'azione irreversibile.
- r8tkt plausibile: prompt injection su `_ruolo_secondo_ai`.
- r8web plausibili: limite_accesso condiviso, CGNAT = doppi medi, `token_di_sistema` senza Mod, revoca OAuth solo locale.
