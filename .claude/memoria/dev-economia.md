# Memoria di dev-economia

## Aggiornata
09/11/2026 · giro r1liv (#124 Livelli), ramo `feat/r1liv`, migrazioni 0581-0589 (0581 usata). Lavoro PER FILE.
09/11/2026 · giro r24fun (migrazioni 0579-0580 usate). 09/11/2026 · giro r21gif, ramo `feat/r21gif`, migrazione 0570 (usata). Lavoro PER FILE.

## In corso
- r3liv (#124, ramo `feat/r3liv`, wt `/home/user/wt-124`, migrazioni 0660-0679): B3-B8 fatti (0660-0665). Restano LIV-013/046 (XP testo e vocale separati), 019 (voto bot, serve elenco bot), 032/033 (annuncio con embed/immagine), 053 (sfondi pronti), 061 (top 10 settimana), 062 (pagina web), 072 (import), 089/090/091 (profilo globale). Prossimo: B9 = 061 + 053 + 032, poi 013/046. Migrazione libera: 0666. `loc.py` in scratchpad.
- Smoke da fare (lo lancia l'orchestratore).

## Fatto
- r3liv B7-B8: 0664 (`text_xp_max`, `xp_percentuale`, pausa 3600), 0665 (`leveling_ruoli_classifica`), `cogs/leveling/ruoli_classifica.py` (lavoro orario, classifica vuota = non toglie niente).
- r3liv B6: 0663 (`colore_testo`, `velo`, `card_colore`, `guild_card_sfondi`), `colore_medio`, `/level rank colore_testo|velo`, `/admin-livelli card sfondo|colore`, `{xp}` nell'annuncio.
- r3liv B5: 0662 (`leveling_reazioni`, `voice_minutes_total`, 3 colonne impostazioni), `add_reaction_xp` (attesa + tetto 50/giorno in una scrittura), `on_raw_reaction_add`, `/admin-livelli guadagno reazioni`, classifica `/level leaderboard` con vocale e reazioni (sempre «di sempre»). `azzera server` non azzera minuti/reazioni.
- r3liv B4: 0661 (`voce_min_persone`, `anti_farm`, `xp_thread/forum/chat_vocale`), `/admin-livelli guadagno vocale|contesti`, `tipo_di_canale`, campo «Come si guadagna XP» in `mostra`; codici già in codice provati in `tests/test_leveling_guadagno_b4.py` (022-025, 028-030, 040, 049, 050, 052, 073, 010).
- r3liv B3: formule (`FORMULE`, `xp_for_level/level_for_xp(…, formula)`), `xp_messaggio`, `ha_prefisso_ignorato`, `e_escluso` con `canali_modo`, `cambia_formula`/`aggiungi_prefisso` nel repo impostazioni, `on_app_command_completion`, `/admin-livelli guadagno formula|messaggi|comandi|prefissi|canali`, 0660.
- r2liv B2: `sincronizza_premi`/`sincronizza_server` e `on_member_join` in `leveling.py`, `rendi_annuncio` in `leveling_logic`, `_prova_annuncio`, `level_reward_repo.add_reward` (tetto 3, blocco per server), 0582 (`leveling_copie_attivita`, `avvisa_dm`, `levelup_testo`); B1: copia+azzeramento in un solo CTE con `FOR UPDATE`.
- r24fun B12: telefono (`cogs/fun/telefono.py`, `core/telefono_logic.py`, `telefono_repo`, 0579-0580, `fun_telefono` spento di base, `/fun telefono`, `/admin-giochi telefono`). Pesi: fun 2604 (14 figli), admin-giochi 2718, giochi 2691: nessun problema. Resta fuori: `/owner telefono` (basta blacklist del bot e `blocca server_id`).
- r23fun B11: `suoni_ruoli` (soundboard.py, `suoni_ruoli_repo`, 0577), `/web turni` (`turni_logic`, `turni_giochi.py`), `/giochi smash` (`smash_logic`, `smash_repo`), `/immagini fusione` (`fusione_logic`, `safe_http.safe_richiesta_byte`). Peso `giochi` 6719 (avviso 6800): un altro figlio va in un sotto-gruppo.
- Giri più vecchi (r1liv, r21-r24, r10-r11, r4-r7): 18 righe compresse; il dettaglio è nella storia di git.

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
- `test_leveling_premi_b2::test_prova_senza_permesso_di_scrittura_non_scrive` fallisce già su main 6d19555d (non mio).
- Klipy: manca l'adattatore (docs non leggibili, serve permesso); si aggiunge a `FONTI_RICERCA`. Splatoon 2 non fatto. Reset WoW EU da confermare dal vivo. `/immagini fusione`: marchio Pokémon, decide l'owner.
- r1liv B1: dopo azzera/ripristina i ruoli-premio non si toccano (arriva con `sincronizza_premi` di B2). `leveling_activity` (classifica mese/settimana) non si azzera con `azzera server`.
- GIF: voci senza fonte (dab, salta, canta, supplica, sposa, fragola, rose, arresta, massaggio, ruba, rombo); Klipy/waifu.im senza adattatore; FUN-136 (azioni del server) non fatta.
- Migrazioni r11: 0410. Embed economia non ancora con miniatura: shop, classifiche, daily/work (testo semplice).
- `test_intent_usage` rosso per file di altri (sondaggi_bottoni, conteggio, messaggi_auto, starboard): non miei.
- Migrazioni mie: 0090-0095, 0097-0099, 0120-0121, 0200-0203, 0340-0341. NON usare 0096.
- #127 restano VOC-006, 010, 013, 014, 016, 017, 021.
- Colonne `boost_expires_at`/`guild_boost_expires_at` nel database, non usate.
