# Memoria di cacciatore-bug

## Aggiornata
21/10/2026 · ultimo giro: `feat/r8uti` (/ruoli D25, scheda, ruoli auto condizioni, suggerimenti, promemoria, sondaggio) con fix c2af58d, 3d722cc, 416859f
16/10/2026 · ultimo giro: `feat/r7mod` (iYokai Mod, catalogo log, NF-30 DM), 5 fix; i 2 lasciati li ha chiusi il revisore.
16/10/2026 · ultimo giro: `feat/r7bak` (/backup D25, copie, modelli, sincronia, chat) con fix 1172556, b70b41f
16/10/2026 · ultimo giro: `feat/r7liv` (vocali opzioni/invita/stato, sfondi card, tick clan raggruppato, /level premi|pause|livelli-recenti) con fix 635507f
14/10/2026 · ultimo giro: `feat/r6ai` (motore AI, /ai, -chiedi, menzione, traduzioni, immagini, ticket) con fix 9516f7c
14/10/2026 · ultimo giro: `feat/r6web` (pannello web, D16)
14/10/2026 · ultimo giro: `feat/r6mod` (massa, verifica tempi, /antiraid, AutoMod r6) con fix
13/10/2026 · ultimo giro: `feat/r4-uti` (ruoli auto, starboard, tag, benvenuto immagine, role menu, embed, contatori, compleanni, inviti, moduli)
13/10/2026 · ultimo giro: `feat/r4-liv` (livelli, economia, giveaway, giochi, profili)
13/10/2026 · ultimo giro: `feat/r4-tkt` (ticket, ModMail, standard/sollecito, log, /voice)

## In corso
- Niente a metà.

## Fatto
- Giri 28/09–11/10 (BUG-19…34, SEC-18…22, F1, boost-146, f7, sicurezza-audit, 147, 66, giro-logt/eco/mod): dettagli in `rapporti/bug.md`.
- giro-core, r3-bak, r3-mus, r4-tkt, r4-uti, r4-liv: alti e medi in `rapporti/bug.md` (13/10). Prove in scratchpad/cb{core,bak,mus,tkt,uti,liv}.
- r6mod (5 fix), r6ai (9516f7c; lasciati: tetto/quota funzione in gara tra persone, prefissi in -chiedi), r6web.
- r8uti: ruoli a scelta ricontrollo permessi, lock massa, condizioni autoruoli in ordine + tetto ridai, tetto promemoria/nel canale.
- r7mod: forum-cache col client di Mod, blocco di 1 msg via Mod, archivio 20k senza tetto, bottone NF-30 ripetuto/ModMail, cache LOG-017 leggi-poi-set.

## Cose imparate
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
- Ordine dei blocchi (clan, batch FOR UPDATE ORDER BY): provare due cicli in parallelo, righe in ordine inverso.
- Router: un UPSERT dal ripiego rende permanente la riga; guardare dopo il cambio del generale.
- Anonimizzare a valore fisso incontra indici unici parziali; registro NF-04: coprire gli action_type dei cog. Ogni tabella nuova: `tests/test_data_registry.py`.
- Regex degli admin: provare `a?`xN+`a`xN, `a{0,99}`xN, `.*.*x$` con timeout.
- Ogni `on_message` con `guild is None` (ModMail, appelli) vede lo STESSO DM: cercare i coordinamenti.
- Ambiente: DB di prova condiviso (`pgrep pytest` prima di fidarsi); prove nei `tests/` con file temporanei poi spostati in scratchpad; cog con `registra_comandi_del_cog(...)`; permessi veri con `discord.Guild/Member(data=..., state=ConnectionState(...))`.
- Sincronie tra server: ricontrollare proprietà all'evento; ruoli per NOME = escalation (confrontare permessi). Caricamenti da file/modello: mai aggiungere permessi pericolosi a @everyone o a ruoli esistenti.
- Modelli scritti dagli admin con str.format: vietare spec/conversioni (`{x:>1e9}`, `{x:{y}}`); sostituire a mano.
- Comandi che fanno creare al bot inviti/link: controllare il permesso di chi chiede.
- AI: ogni lavoro automatico (moderazione, traduzione) che conta sulla persona = aggirabile; cache per somiglianza mai su traduzioni/giudizi.
- Web: `Referrer-Policy: no-referrer` fa mandare `Origin: null` ai POST dei moduli (Fetch spec): rompe il controllo d'origine. `del_cookie` di aiohttp senza `secure=` non cancella i cookie `__Host-`.
- feat/r6mod: corretti 5 (tetto usi/ora ban-kick massa, bulk_ban senza manage_guild, retroattivo solo-sospetti, rientro verify, tetto link/messaggio); 4 plausibili in `rapporti/bug.md`.

## Cose imparate
- Azioni fatte DAL bot (massa, automod) non le vede l'anti-nuke (attore = bot): serve un tetto proprio.
- Lavori nello scheduler legati all'ingresso: cancellarli al rientro (`scheduler.cancel_for_user`).
- wavelink: `Pool.connect` torna con status CONNECTING (CONNECTED col messaggio `ready`); i test con `connetti` finto non lo vedono. Prova con un finto Lavalink aiohttp (/v4/websocket manda ready, /v4/info).
- Ordine blocchi clan: riga membro, `leveling_totals`, poi `clans`. Si prova con due cicli in parallelo e si confronta con la base (`git archive`).
- Controllare sempre l'ordine di avvio (il worker backup non partiva mai), non solo la logica.
- Un fix scritto in un piano può essere sbagliato: si prova, non si copia. BUG-17 era falso positivo: provare la corsa con `tests/support/concorrenza.py`.
- Difetti frequenti: leggi-poi-scrivi su saldi/contatori; risposte oltre i limiti con dati lunghi; azioni fallite riportate come riuscite.
- Cache "leggi, poi set" con await in mezzo: serve un numero di versione. Prove: `ENVIRONMENT=development MAIN_GUILD_ID=1` e token finti.
- Il DB di prova è condiviso: due pytest insieme danno rossi a caso. `pgrep pytest` prima di fidarsi.
- Script fuori dal ramo: `python -m pytest -c pytest.ini --rootdir=. -p tests.conftest -p no:cacheprovider <file in scratchpad>` dalla copia di lavoro; con `-s` il print si vede dopo il "." (grep senza ^).
- Check dei gruppi: `cmd._check_can_run(interaction)` su albero vero; discord.py guarda solo il genitore diretto. Su main i comandi staff non avevano controlli: confrontare con albero vecchio da `git archive`.
- Cog sull'albero VERO: `generate_command_list.py`; DB con maiuscole tra virgolette. I test del cerca-comando mockano i permessi.
- Sicurezza: prove da `tests.test_anti_nuke_f1`; `_solo_chi_gestisce` va cercato su OGNI comando che cambia fiducia/soglie.
- Test di corsa: senza `apri_connessioni` il pool apre le connessioni una alla volta e le due chiamate non si sovrappongono: il test passa anche col codice vecchio. Provare sempre togliendo il fix (mutazione in scratchpad: sottoclasse del repo con l'SQL vecchio, o `_blocco` -> `asyncio.Lock()` nuovo).
- Test con gather che si aspetta "una sola riuscita": controllare se il saldo basta per una seconda acquisto in sequenza (clan: 100000 coin = 25000 + 50000). Ritardare la 2a chiamata di 0,15 s lo mostra.
- Fake `AsyncMock(side_effect=lambda: asyncio.sleep())` NON aspetta: serve `async def`.
- Router/ripiego: ogni `UPSERT` che crea la riga di un tipo dal ripiego la rende permanente: cercare sempre cosa succede dopo che l'admin cambia il generale.
- Batch con FOR UPDATE ORDER BY contro UPDATE di massa senza ordine = deadlock: provare con righe inserite in ordine inverso. `schema_migrations` e' per NUMERO: rinumerare una migrazione gia' girata la fa saltare.
- Prove dentro `tests/` (file temporaneo, poi rm): non usare `-p tests.conftest` (doppia registrazione).
- Anonimizzare a valore fisso (user_id=0) incontra gli indici unici parziali: controllare pg_indexes. Registro NF-04: coprire anche gli action_type scritti dai cog (non solo la colonna generata).
- Chiave multipla (`a,b`): `b64decode` si ferma al primo `=`, quindi la firma dello state usa la prima chiave (a posto). Ogni nuova tabella: lanciare `tests/test_data_registry.py`.
- Permessi veri senza Discord: `discord.Guild/Member/VoiceChannel(data=..., state=ConnectionState(...))` e `channel.permissions_for(m)` (cbtkt/p5b): senza view_channel tutto il resto e' False.
- Regex scritte dagli admin: provare `a?`xN+`a`xN+`c`, `a{0,99}`xN e `.*.*x$` con `multiprocessing` e timeout; i filtri che contano solo `*`/`+` non bastano.
- Ogni listener `on_message` con `guild is None` (ModMail, appello spam-trap) vede lo STESSO DM: cercare i coordinamenti e la blacklist.

- Prove su cog con fake: `registra_comandi_del_cog(cog, gruppi=costruisci_gruppi(), tree=None)`, poi `comandi[nome].callback(cog, inter, ...)`; file temporaneo in tests/ e poi spostato in scratchpad. Controllare sempre i numeri di migrazione contro gli altri rami r4 (`git diff --name-only main...ramo -- core/migrations`).

## Aperto
- r4-tkt: rilievi senza fix in `rapporti/bug.md` (13/10); dopo i fix ripetere p1-p8 di cbtkt.
- Giro mod: lo stato si salva PRIMA dell'azione irreversibile; UPSERT su membro già in stato = perdita dati.
- Rami nuovi: confrontare i numeri di migrazione con gli altri rami aperti; unire i rami r4 in una copia di prova.
- Valori scelti da un utente nelle sostituzioni a catena: `escape_mentions` se `roles=True`.
