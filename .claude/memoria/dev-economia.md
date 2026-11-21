# Memoria di dev-economia

## Aggiornata
17/11/2026 · giro r5eco (#125 Economia e giochi), ramo `feat/r5eco`, wt `/home/user/wt-125`, db `iyokai_w125`, migrazioni 0670-0679 (0670-0672 usate).

## In corso
- r5eco: fatti 16 blocchi (B1-B16: + movimenti, portafoglio, tetto vocale, controllo anti-automazione). Prossimo: 075/076 (rotazione e offerte lampo), 078 ricette, 039, 042-051, 054, 056, 060, 117-119, clan/tesoreria, animali, pesca. `monete` è a 18 figli: nuovi comandi nei sottogruppi `conto` (6) e `rischio` (6), animali/pesca, profilo/missioni. Nuovi comandi admin vanno in `admin-giochi` (admin-economia è a 18 figli: tetto) negozio (061 requisiti, 075-076), B6 giochi a più passi (088 blackjack, 094, 098: serve tabella `economia_partite_aperte` con rimborso all'avvio), B7 clan/tesoreria, B8 animali/pesca. Migrazione libera: 0687 (0687-0689) (restano 0683-0689: una per clan, una per profilo/missioni) (SOLO 0670-0689). `loc.py` della scratchpad è di altri: usare `eco/loc125.py`.
- Smoke da fare (lo lancia l'orchestratore). Test già rossi su main, non miei: `test_data_registry` (guild_card_sfondi, leveling_reazioni, leveling_ruoli_classifica, voice_roles), `test_intent_usage::..._messaggi` (greetings).

## Fatto
- r5eco B16: 0685 (`economia_movimenti`, `voce_max_minuti`), 0686 (`controllo_per_mille`); storico in `add_coins_in`/`spend_coins_in`/daily/lavoro/pay, `/level movimenti`, `core/wallet_card.py` + `/monete conto portafoglio`, `core/anti_automazione.py` (work, daily, mini guadagni), tetto vocale in `compute_voice_minute`. Trappola: i test che sostituiscono `should_trigger_drop` con lambda a 1 argomento: la logica dei drop deve restare a una sola chiamata `should_trigger_drop(roll)`. Mai aggiungere righe a una migrazione già applicata (nemmeno nel proprio DB di test).
- r5eco B15: 0684 (blocchi, amici, matrimoni, prestigio), `sociale_repo`, `cogs/leveling/sociale.py` (`/level sociale ...`, `/monete conto prestigio`), blocchi in pay/regala/duello/tris/forza4, amici senza tassa, prestigio nel lavoro e nel premio (ECO-148, 149, 153-155, 159).
- r5eco B14: 0683 `economia_depositi`, `rischio_repo.blocca/sblocca`, `/monete conto deposito`, `/giochi rps puntata`, `leaderboard solo_presenti`, `cogs/leveling/riffa.py` (ECO-005, 013, 092, 095-097, 119).
- r5eco B13: 0682 (animali, posti, pesci, visti, pesca giorno), `animali_logic`, `animali_repo`, `cogs/fun/animali.py` (`/fun animali ...`, `/fun pesca ...`, ECO-122-124, 130-134, 138). `fun` ha 2 sottogruppi nuovi.
- r5eco B12: 0681 (`shop_items.azione*`), `cogs/leveling/mini_guadagni.py` (`/monete rischio scava|meme|coccole|gratta|bersaglio`), `/admin-giochi oggetto-azione`, azioni in `/monete usa` (ECO-042, 043, 044, 046, 047, 060).
- r5eco B11: 0680 (`lotteria_prezzo`, `rimborso_pct`, 3 tabelle), `lotteria_repo`, `cogs/leveling/lotteria.py` (ECO-117, 118, 121). `monete conto` è a 7 figli.
- r5eco B10: 0679 `economia_potenziamenti`; `potenziamenti_repo`, `cogs/leveling/potenziamenti.py` (potenzia, scrigno, guadagni), tasso del giorno in `/monete vendi`, `tavolo_logic`, `cogs/fun/tavolo.py` (tris, forza4) (ECO-077, 079, 081, 082, 107-109).
- r5eco B9: 0678 (`msg_coins*`, `stipendio_*`, 4 tabelle), `stipendi_repo`, `cogs/leveling/stipendi.py`, `passi_logic`, `cogs/fun/giochi_passi.py` (ECO-033-038, 094, 098).
- r5eco B7-B8: 0676 `economia_duelli`, 0677 `economia_partite_aperte`; `duello_logic`, `duelli_repo`, `blackjack_logic`, `partite_repo`, `cogs/fun/sfide.py` (`/giochi sfide duello|duelli`), `cogs/fun/blackjack.py` (ECO-088/089 senza divisione, 104, 106).
- r5eco B6: 0675 (`banca_total`, `furto_*`/`colpo_successo`, `economia_pause`, `economia_lavoro`), `rischio_logic`, `rischio_repo`, `cogs/leveling/rischio.py` (`/monete conto banca|lavoro|dimettiti`, `/monete rischio colpo|avventura|furto|elemosina|cerca`), paga del `/monete work` per turni (ECO-004/029/030/031/032/040/041/156 parziale).
- r5eco B5: 0674 `economia_eventi`, `cogs/leveling/evento_monete.py` (`/admin-giochi evento avvia|chiudi`, ECO-057). Merge di main fatto (f083dfce).
- r5eco B4: 0673 (`drop_*` in leveling_settings, `economia_lasciti`), `lasciti_repo`, `cogs/leveling/drop.py`, `_drop_casuale` in leveling.py (ECO-052/053/055). Test `test_drop_behavior` rimessi in piedi (fake con content/attachments).
- r5eco B3 (1128615e): 0672 `economia_inventario`+`shop_items.regalabile`, `inventario_repo`, `cogs/leveling/inventario.py` (ECO-058/059/070-073/086).
- r5eco B2 (a88b13cd): 0671 `economia_giochi_stat`, roulette/carta/scala in `coin_games_logic`, `cogs/fun/giochi_monete.py` (`esegui_partita`), puntate e pausa del server anche in `/giochi gioca` (ECO-021/022/090/099/100/115/116).
- r5eco B1 (696c9de4): 0670 (colonne in `leveling_settings` + `economia_accrediti_iniziali`, `economia_premi_periodici`), `economia_repo`, `cogs/leveling/economia.py`, tetto al saldo in `add_coins_in`/`_riscuoti_premio`/`gioca`/`transfer_coins` (ECO-002/003/008/010/012/014/019/023-026/028).
- r3liv B3-B8: formule, XP reazioni/vocale/contesti, card, ruoli di classifica (0660-0665).
- Giri più vecchi (r1liv-r2liv, r21-r24, r10-r11, r4-r7): nella storia di git.

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

- Tetto al saldo: usare `somma_con_tetto_sql`/`valore_nuovo_con_tetto_sql` (leveling_repo) in ogni nuova scrittura che accredita; `refund_coins_in` e lo staff restano senza tetto. `add_item` restituisce l'id (non l'oggetto). CHECK su quantità: `>= 0` se si decrementa prima di pulire.
- Un cog nuovo per ogni blocco (leveling.py ha 4600 righe). Testi: `loc.py` in scratchpad (it, en, nomi, desc). Nuovi `on_member_*` in `core/intent_usage.py` e rigenerare `docs/INTENT_PRIVILEGIATI.md`.

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
