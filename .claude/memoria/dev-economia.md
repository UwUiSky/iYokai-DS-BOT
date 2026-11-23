# Memoria di dev-economia

## Aggiornata
23/11/2026 · giro r1rep (#124, #125, #122), ramo `feat/r1rep`, wt `/home/user/wt-rep`, db `iyokai_wrep`, migrazioni 0870-0872 USATE (restano 0873-0879). Voci della scheda fatte (D120). Smoke da fare.

## In corso
- Niente di aperto. Prossimo giro: ECO con motivo in D86 (075/076/078 già fatte) e voci «da fare» del catalogo (`CONTROLLO_AREE_CHIUSE.md`).
- Smoke da fare (lo lancia l'orchestratore). Test già rossi su main, non miei: `test_riferimenti_comandi` (`/opzioni` in `web_panel_ticket_trascrizioni.py`).

## Fatto
- r1rep: reputazione (0870; `/rep`, `/admin-rep`, `reputazione_repo`, `reputazione_logic`, «grazie @utente» in `on_message`), annuncio con embed e card (0871, `render_levelup_card`), import da file (`/admin-livelli azzera importa`, `livelli_importa` in `livelli_funzione`), `/level progressi carta:sì` (LIV-089), modulo voto (0872; `voto_server` su `VOTO_PORT`, `VOTO_SEGRETO` nel .env, `/monete conto voto`, `/admin-giochi voto`, bonus XP via `_fattore_voto`).
- r6eco (0687-0689, 0790-0792): D104, D105; r5eco B1-B17 (0670-0686): economia, giochi, rischio, lotteria, animali, sociale, controllo area 17 (D86, D103).
- r3liv: formule, XP reazioni/vocale, card, ruoli di classifica (0660-0665). Giri più vecchi: nella storia di git.

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
- `Config` è frozen: nei test si sostituisce una funzione del modulo (`modulo_acceso`), non il campo. `nomi` di `comandi.json` en-US solo per nomi di comandi (non parametri).
- Nuovo gruppo di primo livello: va in `command_groups._DEFINIZIONI`, `tests/support/command_policy.py` e `tests/test_command_groups.py` (ordine = ordine dei cog).
- Un voto o un «grazie» rinviato dal sito: pausa/dedup nella stessa transazione, con `pg_advisory_xact_lock(hashtextextended(...))`; niente conteggi fuori transazione.

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
