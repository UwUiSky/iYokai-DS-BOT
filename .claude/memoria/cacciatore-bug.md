# Memoria di cacciatore-bug

## Aggiornata
12/10/2026 · ultimo giro: `feat/r3-bak` (backup D8, restore OAuth, cifratura v2)

## In corso
- Niente a metà. Giro eco chiuso. Prove: scratchpad/cbeco (p1 decadimento, p2 corse, p3 deadlock, p6 card, p7 migrazioni, test_prove_eco*.py).

## Fatto
- Revisione correzioni 28/09–01/10 (BUG-19…34, SEC-18…22): tutti risolti in R1-bis, tranne 26/28/29 superati (D8).
- Giri F1 05/10 (f1-133/134/135): pochi rilievi minori; uno vero: deadlock `set_member_role` vs `apply_text_tick`.
- feat/boost-146: nessun bug vero (migrazione 0020 ok, niente deadlock). 3 note basse.
- feat/f7-quadro e f7-decoratore: 1 alto latente (sotto-gruppo `Group` non eredita il check); matrice 252 foglie x 8 profili senza regressioni.
- feat/sicurezza-audit: 6 alti (limits/punish/recovery senza `_solo_chi_gestisce`, extra owner declassa extra owner, punizione a ogni evento, antiraid aperto, quarantena fail-open, revoca ban globale). Prove: cbsic_proofs.
- feat/147-cerca-comando: 0 alti; cache ID sotto lock senza timeout, `invalida()` perso se la fetch fallisce.
- feat/66-utility: 0 alti. Sticky: il blocco per canale regge (10 messaggi = 1 invio; senza blocco 8). Ping D12, lunghezze dopo segnaposto, 25/2000/4096, SQL condizionato, modules_updated: a posto. Rilievi: role menu pubblica-poi-salva perde opzioni con due admin; `ping_ruoli` si azzera al toggle; `/sticky-set` durante repost; 2 test "doppio clic" dei suggerimenti vuoti. Test instabile del canale clan = test fragile, non codice.
- feat/giro-logt: 1 alto (riga fantasma del router dopo canale generale cancellato), 6 medi (post forum doppi, avviso perso, audit per tempo, snipe di mod, ticket+forum).
- feat/giro-eco: 0 alti. SQL del decadimento = funzione pura (50000 saldi fino a 9e18), corse e doppio versamento a posto. Medi: deadlock batch vocale vs decadimento, "sostituisci" toglie senza dare, categoria esclusa inutile, migrazioni rinumerate (versione per numero), test senza permessi/lock.
- feat/giro-mod: 2 alti (secondo isolamento sovrascrive i ruoli salvati; clear `channel` senza permessi sul canale) + crash tra edit ruoli e stato; medi: job vecchio rilascia isolamento nuovo, appello accettato revoca tutto/unban fallito, verify non-verificato=verifica, invito perso con DM chiusi. IDOR appelli e permessi Accetta/Rifiuta: a posto.

- feat/giro-core: 2 alti (contatore casi purgato con ban trattenuti; server riaggiunto a bot spento mai piu' purgato) + export con dati altrui (alto). Medi: ticket aperti user_id=0 (unico), clan senza titolare, escalation non trattenuta, rinnovo token cancella su 429/5xx, cache premium gara, sban programmato purgato. Prove: scratchpad/cbcore. Cricchetto max_length: ok.

- feat/r3-bak: 2 alti (get_token None su riga illeggibile = bannito riinvitato; Creator senza permessi/Forbidden su ruoli). Medi: collega senza controlli sul server, 2 codici=2 job, finalize salta blacklist, 429 sul rinnovo, restore senza blocco, tabelle 0070 fuori dal registro. Prove: scratchpad/cbbak (env.sh, p1-p5).

- feat/r3-mus (musica F2): 3 alti (nodo sano scartato perche' ancora CONNECTING; worker assegnato due volte; `//percorso` grezzo a Lavalink), medi: `play` stesso canale rilascia la sessione viva, `previous` avanti-indietro, `inactive_channel_tokens=None` su tutto il nodo locale. Prove: scratchpad/cbmus (fake_lavalink.py riusabile).

## Cose imparate
- wavelink: `Pool.connect` torna con status CONNECTING (CONNECTED col messaggio `ready`); i test con `connetti` finto non lo vedono. Prova con un finto Lavalink aiohttp (/v4/websocket manda ready, /v4/info).
- Env per script fuori dai test: `.env.example` con i vuoti riempiti da `fake_<NOME>`, `*_ID=1`.
- Ordine blocchi clan: riga membro, `leveling_totals`, poi `clans`. Si prova con due cicli in parallelo e si confronta con la base (`git archive`).
- Controllare sempre l'ordine di avvio (il worker backup non partiva mai), non solo la logica.
- Un fix scritto in un piano può essere sbagliato: si prova, non si copia. BUG-17 era falso positivo: provare la corsa con `tests/support/concorrenza.py`.
- Difetti frequenti: leggi-poi-scrivi su saldi/contatori; risposte oltre i limiti con dati lunghi; azioni fallite riportate come riuscite.
- Cache "leggi, poi set" con await in mezzo: serve un numero di versione. Prove: `ENVIRONMENT=development MAIN_GUILD_ID=1` e token finti.
- Il DB di prova è condiviso: due pytest insieme danno rossi a caso. `pgrep pytest` prima di fidarsi.
- `core.config` fuori dai test: righe di `.env.example` e `PREMIUM_ALPHA_UNLOCK_ALL=false`.
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

## Aperto
- Giro a fine F1 sulle aree toccate il 05/10 (sicurezza, moderazione, log, ticket, vocali, livelli, clan).
- Rilievi senza fix: issue #133–#137 e nuovi di 11/10 (vedi `rapporti/bug.md`).
- Giro mod: i comandi di sanzione devono salvare lo stato PRIMA dell'azione irreversibile; UPSERT di stato da membro gia' in stato = perdita dati. Prove: `Scena` di test_moderation_tempban_modi riusabile.
