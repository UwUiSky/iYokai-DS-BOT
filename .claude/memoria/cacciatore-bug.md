# Memoria di cacciatore-bug

## Aggiornata
21/10/2026 · ultimi giri: `feat/r8tkt` (opzioni ticket #120, AI #139; 6 fix 92633fa…f8c87c8, i 4 lasciati li ha chiusi il revisore), `feat/r8web` (6 fix ec769c2…6de5e0f), `feat/r8uti` (c2af58d, 3d722cc, 416859f).
16/10/2026 · r7mod, r7bak (1172556, b70b41f), r7liv (635507f). 14/10 r6ai (9516f7c), r6web, r6mod. 13/10 r4-tkt/uti/liv.
21/10/2026 · ultimo giro: `feat/r9nsfw` (bot NSFW, App utente), 5 fix: 644985d, a5dc0b2, c93a382, b4a0667, 9aaf9dd.
21/10/2026 · ultimo giro: `feat/r8web` (verifica web NF-21, #148, marchio, aspetto, «I miei dati»), 6 fix: ec769c2, 0e8943c, 87f72f9, 951cf86, db91e8c, 6de5e0f.
16/10/2026 · r7mod, r7bak, r7liv (fix in `rapporti/bug.md`).

## In corso
- Niente a metà.

## Fatto
- Giri 28/09–14/10 (BUG-19…34, SEC-18…22, F1, giro-core, r3, r4-*, r6*, r7*): dettagli in `rapporti/bug.md`. Prove in scratchpad/cb*.
- r8tkt: link citato (titolare + thread privati), ruoli durante = self-service, AI scelta conta_utente, richiesta chiusura annullata se l'utente scrive, tetto pannello sotto blocco, osservatori non chiudono.
- Giri 28/09–14/10 (BUG-19…34, SEC-18…22, F1, giro-core, r3, r4-*, r6*): dettagli in `rapporti/bug.md`.
- r7mod, r7bak (1172556, b70b41f), r7liv (635507f).
- r9nsfw: filtro Unicode/composti, tetto Segnala, D6 bot NSFW, App fuori server = DM.
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
- Regole con condizioni (richiesti/esclusi): valutarle in ordine contando i ruoli già scelti; «ridai se tolto» = ping-pong senza tetto. Self-service: ricontrollare i permessi al momento della presa, non solo all'aggiunta.
- `monkeypatch.setattr(modulo.asyncio, "sleep", ...)` cambia asyncio.sleep per TUTTI: per cedere il turno usare un future con call_soon.
- Due client (Mod/principale): ogni oggetto in cache porta il SUO client; cache condivise separate per bot. `http.*` via Mod salta i casi speciali di discord.py (1 messaggio…).
- Stato solo in memoria: chi lo svuota (evento spento, richiesta privacy NF-04, riavvio).
- Azioni fatte DAL bot non le vede l'anti-nuke (attore = bot): serve un tetto proprio.
- Difetti frequenti: leggi-poi-scrivi su saldi/contatori; cache "leggi, poi set" con await in mezzo (serve una versione); risposte oltre i limiti; azioni fallite riportate come riuscite.
- Test di corsa: `tests/support/concorrenza.apri_connessioni`, sempre provati togliendo il fix (mutazione in scratchpad). Fake `AsyncMock(side_effect=lambda: asyncio.sleep())` NON aspetta: serve `async def`.
- AI: lavoro automatico che conta sulla persona = aggirabile; niente cache per somiglianza su traduzioni/giudizi.
- Web: `Referrer-Policy: no-referrer` manda `Origin: null` nei POST; `del_cookie` senza `secure=` non cancella `__Host-`.
- Lavori nello scheduler legati all'ingresso: cancellarli al rientro. Controllare anche l'ordine di avvio.
- wavelink: `Pool.connect` torna CONNECTING; provare con un finto Lavalink aiohttp.
- Ordine blocchi (clan, batch FOR UPDATE ORDER BY): due cicli in parallelo, righe in ordine inverso. `schema_migrations` è per NUMERO: confrontare i numeri con gli altri rami aperti.
- Router: un UPSERT dal ripiego rende permanente la riga.
- Anonimizzare a valore fisso incontra indici unici parziali. Ogni tabella nuova: `tests/test_data_registry.py`; nell'export guardare le colonne di TERZI (colonne_utente doppie = id dell'altro nella copia).
- Regex degli admin: `a?`xN+`a`xN, `a{0,99}`xN, `.*.*x$` con timeout. Modelli str.format: vietare spec/conversioni.
- Ogni `on_message` con `guild is None` vede lo STESSO DM: cercare i coordinamenti.
- Ambiente: DB condiviso tra worktree (`pgrep pytest`); prove in `tests/test_tmp_*.py` poi spostate in scratchpad (non `-p tests.conftest`); permessi veri con `discord.Guild/Member(data=..., state=ConnectionState(...))`.
- Sincronie tra server: ricontrollare proprietà all'evento; ruoli per NOME = escalation. Caricamenti da file: mai permessi pericolosi a @everyone.
- Comandi che fanno creare al bot inviti/link: controllare il permesso di chi chiede.
- Web: `Referrer-Policy: no-referrer` → `Origin: null` nei POST; `del_cookie` senza `secure=` non cancella `__Host-`. aiohttp ≥3.12: `request.multipart()` limita OGNI parte a `client_max_size`: per i caricamenti un `MultipartReader` proprio. Access log: ogni percorso con id di persona va redatto (c'è l'IP accanto). `str.isdigit()` accetta "²".
- Filtri di parole: NFKD non basta (cirillico, Cf invisibili); cercare dentro le parole (tag composti) e a lettere unite. Bot separati: D6 sulla presenza di QUEL bot. App utente: `is_guild_integration()` falso = server senza bot, trattare come DM.
- Impronte/IP: dietro proxy non dichiarato tutti hanno lo stesso IP interno → doppi falsi e limiti per IP condivisi. Un link/modulo riusabile che avvisa lo staff: deduplicare l'avviso.

## Aperto
- r4-tkt: rilievi senza fix in `rapporti/bug.md` (13/10).
- Giro mod: lo stato si salva PRIMA dell'azione irreversibile.
- r8tkt plausibile: prompt injection su `_ruolo_secondo_ai`.
- r8web plausibili: limite_accesso condiviso, CGNAT = doppi medi, `token_di_sistema` senza Mod, revoca OAuth solo locale.
