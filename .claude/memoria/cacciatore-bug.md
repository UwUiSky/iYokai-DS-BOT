# Memoria di cacciatore-bug

## Aggiornata
14/10/2026 · ultimo giro: `feat/r6web` (pannello web, D16)
13/10/2026 · ultimo giro: `feat/r4-uti` (ruoli auto, starboard, tag, benvenuto immagine, role menu, embed, contatori, compleanni, inviti, moduli)
13/10/2026 · ultimo giro: `feat/r4-liv` (livelli, economia, giveaway, giochi, profili)
13/10/2026 · ultimo giro: `feat/r4-tkt` (ticket, ModMail, standard/sollecito, log, /voice)

## In corso
- Niente a meta'. Giro r4-tkt chiuso e pushato. Prossimo: riprova dei fix con cbtkt/test_p*.py dalla copia `wt/tkt`.

## Fatto
- Revisione correzioni 28/09–01/10 (BUG-19…34, SEC-18…22): tutti risolti in R1-bis, tranne 26/28/29 superati (D8).
- Giri F1 05/10 (f1-133/134/135): pochi rilievi minori; uno vero: deadlock `set_member_role` vs `apply_text_tick`.
- Giri 06-11/10 (boost-146, f7-quadro/decoratore, sicurezza-audit 6 alti, 147-cerca-comando, 66-utility, giro-logt, giro-eco, giro-mod 2 alti): dettagli in `rapporti/bug.md`.
- feat/giro-core: 2 alti (contatore casi purgato con ban trattenuti; server riaggiunto a bot spento mai piu' purgato) + export con dati altrui (alto). Medi: ticket aperti user_id=0 (unico), clan senza titolare, escalation non trattenuta, rinnovo token cancella su 429/5xx, cache premium gara, sban programmato purgato. Prove: scratchpad/cbcore. Cricchetto max_length: ok.
- feat/r3-bak: 2 alti (get_token None su riga illeggibile = bannito riinvitato; Creator senza permessi/Forbidden su ruoli). Medi: collega senza controlli sul server, 2 codici=2 job, finalize salta blacklist, 429 sul rinnovo, restore senza blocco, tabelle 0070 fuori dal registro. Prove: scratchpad/cbbak (env.sh, p1-p5).
- feat/r3-mus (musica F2): 3 alti (nodo sano scartato perche' ancora CONNECTING; worker assegnato due volte; `//percorso` grezzo a Lavalink), medi: `play` stesso canale rilascia la sessione viva, `previous` avanti-indietro, `inactive_channel_tokens=None` su tutto il nodo locale. Prove: scratchpad/cbmus (fake_lavalink.py riusabile).
- feat/r4-tkt (ticket NF-13, ModMail, standard/sollecito, log, /voice): 4 alti (`/voice nascondi` blocca tutti e il bot; regex `a?`x24 e `.*.*` x5 bloccano il loop; DM doppio ModMail+appello spam-trap; risposte standard con dati utente fuori dal registro), 11 medi/bassi. Prove: scratchpad/cbtkt (env.sh, test_p1..p8, p4_regex.py, p5b_perm.py).

- feat/r4-uti: 2 alti di unione (migrazione 0091 doppia con r4-liv; `/gestione` 8400 e `/admin` 8293 > 8000 con liv+tkt). Medi: `{displayname}` non scappato (ping ruolo), starboard da canali privati, TOCTOU unique/binding, compleanno rifatto a ogni `imposta`, memoria ruoli (pending/raid/ruoli a tempo), `_join_results` stantio al rientro. Prove: scratchpad/cbuti (p1-p4, mm = unione di prova).
- feat/r4-liv: 1 alto (`/gestione xp livello` 10M = loop fermo, level_for_xp lineare), medi: gerarchia attore su ruoli-premio, cooldown /fun gioca aggirato, mark_ended non e' claim, elenco modelli >2000, programmato muto senza permessi, migrazione 0091 doppia con r4-uti. Monete (shop, profilo, gioca, pay, modifica): 120 operazioni insieme, mai negativo, scorte esatte. Prove: scratchpad/cbliv (h.py, p1-p3, test_prove_liv.py).

## Cose imparate
- Web: `Referrer-Policy: no-referrer` fa mandare `Origin: null` ai POST dei moduli (Fetch spec): rompe il controllo d'origine. `del_cookie` di aiohttp senza `secure=` non cancella i cookie `__Host-`.
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
- Rilievi r4-tkt senza fix: vedi `rapporti/bug.md` (13/10); dopo i fix ripetere p1-p8 di cbtkt (vecchi giri: #133-#137).
- Giro mod: i comandi di sanzione devono salvare lo stato PRIMA dell'azione irreversibile; UPSERT di stato da membro gia' in stato = perdita dati. Prove: `Scena` di test_moderation_tempban_modi riusabile.
- Unire i rami r4 in una copia di prova (`git clone` + merge, docs `--ours`): numeri di migrazione doppi e caratteri per gruppo (`albero.py`) si vedono solo cosi'. Ogni ramo nuovo: confrontare numeri 00xx con gli altri rami aperti.
- Sostituzioni a catena (`str.replace`) e segnaposto nuovi: ogni valore scelto da un utente (nome visualizzato) va scappato con `escape_mentions` se `roles=True`.
