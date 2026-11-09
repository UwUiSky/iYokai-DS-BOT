# Memoria di dev-economia

## Aggiornata
09/11/2026 · giro r1liv (#124 Livelli), ramo `feat/r1liv`, migrazioni 0581-0589 (0581 usata). Lavoro PER FILE.
09/11/2026 · giro r24fun (migrazioni 0579-0580 usate). 09/11/2026 · giro r21gif, ramo `feat/r21gif`, migrazione 0570 (usata). Lavoro PER FILE.

## In corso
- r2liv B2 (#124) fatto (0582). Prossimo: B3 guadagno XP (006, 007, 017, 018, 021, 004; 0583) secondo `/home/claude/wt/disegno_livelli.md`, comando nuovo `/admin-livelli guadagno`. `test_add_voice_minute_rollover_giornaliero` fallisce a cavallo del cambio di data (non mio).
- r23fun (B10-B11 di #131) finito, ramo `feat/r23fun`, worktree `/home/claude/wt/r23fun`, env `/tmp/env_w23fun.sh`. Migrazioni usate: 0576, 0577 (le 0572-0575 erano di r22fun). Prossimo: niente; resta tetto Premium battitura (con dev-core), Klipy e Splatoon 2.
- Smoke da fare (lo lancia l'orchestratore).

## Fatto
- r2liv B2: `sincronizza_premi`/`sincronizza_server` e `on_member_join` in `leveling.py`, `rendi_annuncio` in `leveling_logic`, `_prova_annuncio`, `level_reward_repo.add_reward` (tetto 3, blocco per server), 0582 (`leveling_copie_attivita`, `avvisa_dm`, `levelup_testo`); B1: copia+azzeramento in un solo CTE con `FOR UPDATE`.
- r24fun B12: telefono (`cogs/fun/telefono.py`, `core/telefono_logic.py`, `telefono_repo`, 0579-0580, `fun_telefono` spento di base, `/fun telefono`, `/admin-giochi telefono`). Pesi: fun 2604 (14 figli), admin-giochi 2718, giochi 2691: nessun problema. Resta fuori: `/owner telefono` (basta blacklist del bot e `blocca server_id`).
- r23fun B11: `suoni_ruoli` (soundboard.py, `suoni_ruoli_repo`, 0577), `/web turni` (`turni_logic`, `turni_giochi.py`), `/giochi smash` (`smash_logic`, `smash_repo`), `/immagini fusione` (`fusione_logic`, `safe_http.safe_richiesta_byte`). Peso `giochi` 6719 (avviso 6800): un altro figlio va in un sotto-gruppo.
- r23fun B10: `core/lemmy_logic.py`, `immagini_segnalazioni_repo` (0576), `cogs/fun/immagini_comunita.py` (`/immagini post`, `/admin-giochi servizi`), `/gif cerca` in `gif.py`; interruttori `fun_immagini_post`/`fun_gif_cerca` (scheda «fun»), spenti di base. Klipy non fatto (docs illeggibili).
- r1liv #124: B1 fatto (commit unico). Prossimo: B2 premi (042, 043, 047, 034, 038; 0582) secondo `/home/claude/wt/disegno_livelli.md`. `/admin-livelli` pesa 2952 (misura r1liv), ampio margine.
- r22fun (B6-B9 di #131, D70), ramo `feat/r22fun`, worktree `/home/claude/wt/r22fun`, env `scratchpad/env_r22fun_dev.sh`. Previsione: 4 commit (B6 quiz, B7 gruppo, B8 carte, B9 schede). B6-B9 fatti (4 commit). Resta: tetto Premium testi battitura (D59, con dev-core); servizi giochi B10+ non richiesti.
- Smoke da fare (lo lancia l'orchestratore).

## Fatto
- r1liv B1: `/admin-livelli azzera server|ripristina|auto` + `diagnosi` in `cogs/leveling/azzeramenti.py` (cog nuovo, `AzzeramentiCog`), `core/leveling_azzera_logic.py`, `repositories/leveling_copie_repo.py`, 0581 (`leveling_copie`, `leveling_copie_righe`, 4 colonne in `leveling_settings`), blocco 071 anche in `/admin-livelli membro`.
- r22fun B9: `/web scheda` in `cogs/fun/schede_giochi.py` + `core/schede_giochi_logic.py` (NON `schede_logic`/`SchedeCog`: esistono in utility), `safe_http.safe_richiesta`, 0575 `cache_esterna`.
- r22fun B8: `core/carte_logic.py`, `fun_impostazioni_repo`, `cogs/fun/carte.py`, `data/carte/*.json` (carte originali).
- r22fun B7: `core/gruppo_logic.py`, `battitura_repo`, `cogs/fun/_lobby.py`, `giochi_gruppo.py`, 0574; tetto Premium D59 non collegato.
- r22fun B6: quiz (`core/quiz_logic.py`, `quiz_repo`, `cogs/fun/quiz.py`, 0572/0573, `fun_gare_repo.aggiungi_punti`).
- r21fun B5: 7 effetti immagine (062/064), 3 scherzi (063) in `fun_extra.py`.
- r21fun B4: animal 5 specie + `quante`, `/immagini foto|xkcd`, `core/xkcd_fetcher.py`, `fetch_immagini`. r21fun B3: 0571 `fun_punteggi`/`fun_mazzi`, `fun_gare_repo`, `fun_gare_logic`, `/giochi dado|spinner|mazzo`, `/admin-giochi punteggi azzera`.
- r21fun B2: `core/fun_piccoli_logic.py`, `cogs/fun/giochi_extra.py` (`/giochi minato`), coinflip `quante`, ship `tema`, joke `chuck`, casuale `classe`.
- r21gif: `core/gif_catalogo.py`, `core/gif_fonti.py`, `core/gif_logic.py`, `cogs/fun/gif.py`, `data/gif_catalogo.json`, 0570 (`gif_privacy`, `gif_blocchi`); `/gif reazione|azione|privacy`.
- r11: D38 `core/moneta_server.py`, `guild_coin_images` (0410), miniatura `moneta.png` in saldo/cassa/giochi/clan info; D30 `MUSIC_TOKEN_6..20`, `MusicFleet.total_workers`, test radio solo owner.
- r10: SPEC §15 `[~]`→`[x]` con le prove già nei test (erano marcatori vecchi del 04/10); ECO-063/065/066/067/068 shop (`shop_repo`, `togli_ruoli_shop_scaduti` nel cog, 0340); LIV-058 (`week_key` in `leveling_activity`); ECO-001/ECO-015 (0341).
- r7 D: `/level premi` (LIV-048/027), `/level pause` (ECO-020), `/level livelli-recenti` (LIV-039, 0203).
- r4-r7 (vecchi): F1 unito `9db9e8a`, NF-12/NF-40 card, #65 tick vocale, NF-25/32. r7 A: #144 blocco vocale salvato nel DB (0200, `segna_bloccato`/`togli_blocco`); #127 VOC-007 invita, 008 stato, 011/012 nome da modello e numeri, 015 nascono bloccati, 018 registro (`/gestione voice opzioni`, 0201).

## Cose imparate
- Il bot dei test (`fake_member(bot=True)`) non ha `manage_roles`: nei test dei ruoli-premio va dato `guild_permissions=Permissions(manage_roles=True)`. Un nuovo ascoltatore di eventi membri va in `core/intent_usage.py` e `docs/INTENT_PRIVILEGIATI.md` si rigenera con `genera_documento()`.
- Azzeramenti: copia + UPDATE nella stessa transazione, `pg_advisory_xact_lock` per server (due azzeramenti insieme = una copia sola); mai copie vuote. Ripristino: `ON CONFLICT ... WHERE EXCLUDED.xp_total > t.xp_total` (non toglie mai XP, si può ripetere). `get_config(guild, fresco=True)` salta la cache di 60 s per i controlli di blocco. `on_member_remove` scatta anche col ban: «uscita» aspetta 3 s e guarda la cache dei bannati.
- Nei test dei bottoni dopo `defer()` il finto ha `is_done()` False: impostarlo a mano se il codice poi usa il followup.
- Prima di creare un file in `core/` o una classe cog: `ls`/grep del nome (esistono `core/schede_logic.py` e `SchedeCog` in utility). `test_riferimenti_comandi` legge i f-string con `/parola`: costruire gli URL con `"/".join`. Tetto con `COUNT` + INSERT: prima `pg_advisory_xact_lock` in transazione, poi l'INSERT (snapshot nuovo).
- Cooldown + record in una sola INSERT: nel `DO UPDATE` serve `WHERE aggiornato <= now()-intervallo`, altrimenti due clic insieme passano. `testo_per` nelle risposte pubbliche (anche etichette bottone) vuole `pubblica=True`. `locales/en-US/comandi.json`: descrizioni sotto `"descrizioni"`.
- Migrazioni: mai modificare una già applicata; una nuova per ogni aggiunta.
- Soldi: una UPDATE condizionata; pagamento + effetto in una transazione con `FOR UPDATE`; scorte prima dei coin.
- Giochi con le monete: `leveling_repo.gioca` (una UPDATE), mai nella classifica del mese.
- Modifiche staff (xp/monete) scrivono solo `leveling_totals`.
- `tests/test_repository_callers.py`: ogni metodo di repo ha un chiamante di produzione.
- Test di concorrenza: `apri_connessioni(pool)` prima di `asyncio.gather`.
- F7: nei test `cog.metodo.callback(cog, ...)`; fixture con `LevelingCog(bot=None)` deve essere `async def`.
- Blocchi: `ORDER BY user_id` prima di `FOR UPDATE`; righe nuove vuote con `ON CONFLICT DO NOTHING`.
- Rank card: Pillow in `run_image_task`, avatar con `safe_open_image`, ricade sull'embed.
- `locales/comandi.en.json`: formato `indent=1`, ordine d'inserimento; "nomi" solo per nomi di comandi (non parametri: il test li rifiuta). Script in scratchpad `eco/tradu.py`.
- Peso gruppi: script scratchpad `eco/pesi.py <gruppi>` (gestione ~6000, level ~4700, fun 25 figli pieno).
- Finti dei canali vocali: `overwrites_for` deve restituire un `PermissionOverwrite` vero (il repo lo salva).
- `leveling_settings_repo` ha cache di 60 s sul singleton: un test che cambia le impostazioni la svuota alla fine (altrimenti sporca i test dopo).
- Output dei test lunghi: `-p no:warnings` e log nella scratchpad; il traceback di birthdays a fine run è rumore.

- Marcatori `[~]` con «Stato 04/10» spesso sono vecchi: prima grep dei test, poi il codice, poi si decide.
- Ruolo dello shop a tempo: alla scadenza `shop_purchases.role_id` va a NULL (l'indice unico dei ruoli lascia ricomprare, lo storico resta).
- Righe di `leveling_activity`: mese `2026-10` e settimana `2026-W43`; chi cerca «la riga del mese» filtri per `period_key`.
- GIF: nuove fonti si aggiungono in `FONTI` (gif_fonti.py) con adattatore in `_richiesta` e `leggi_risposta`; categorie sempre in `voce.fonti`, mai da testo libero; test `test_gif_fonti` verifica SFW.
- `testi.json` si riscrive con `json.dumps(indent=2, ensure_ascii=False)+"\n"`; `comandi.json` en-US con `indent=1`. Un nuovo gruppo top-level va in `AUDIENCE` di `tests/support/command_policy.py`. Un testo in `core/` che contiene `/parola` tra apici è letto come comando citato.

## Aperto
- Klipy: manca l'adattatore (docs non leggibili, serve permesso); si aggiunge a `FONTI_RICERCA`. Splatoon 2 non fatto. Reset WoW EU da confermare dal vivo. `/immagini fusione`: marchio Pokémon, decide l'owner.
- r1liv B1: dopo azzera/ripristina i ruoli-premio non si toccano (arriva con `sincronizza_premi` di B2). `leveling_activity` (classifica mese/settimana) non si azzera con `azzera server`.
- GIF: voci senza fonte (dab, salta, canta, supplica, sposa, fragola, rose, arresta, massaggio, ruba, rombo); Klipy/waifu.im senza adattatore; FUN-136 (azioni del server) non fatta.
- Migrazioni r11: 0410. Embed economia non ancora con miniatura: shop, classifiche, daily/work (testo semplice).
- `test_intent_usage` rosso per file di altri (sondaggi_bottoni, conteggio, messaggi_auto, starboard): non miei.
- Migrazioni mie: 0090-0095, 0097-0099, 0120-0121, 0200-0203, 0340-0341. NON usare 0096.
- #127 restano VOC-006, 010, 013, 014, 016, 017, 021.
- Colonne `boost_expires_at`/`guild_boost_expires_at` nel database, non usate.
