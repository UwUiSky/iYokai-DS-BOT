# Memoria di dev-economia

## Aggiornata
09/11/2026 · giro r21gif, ramo `feat/r21gif`, migrazione 0570 (usata). Lavoro PER FILE.

## In corso
- r21fun (B2-B5 di #131, D70), ramo `feat/r21fun`, worktree `/home/claude/wt/r21fun`, env `scratchpad/env_r21fun_dev.sh`. Previsione: 4 commit. B2, B3 fatti; poi B4, B5. `fun citazioni caso` (030) NON c'è su main: saltata.
- Smoke da fare (lo lancia l'orchestratore).

## Fatto
- r21fun B3: 0571 `fun_punteggi`/`fun_mazzi`, `fun_gare_repo`, `fun_gare_logic`, `/giochi dado|spinner|mazzo`, `/admin-giochi punteggi azzera`.
- r21fun B2: `core/fun_piccoli_logic.py`, `cogs/fun/giochi_extra.py` (`/giochi minato`), coinflip `quante`, ship `tema`, joke `chuck`, casuale `classe`.
- r21gif: `core/gif_catalogo.py`, `core/gif_fonti.py`, `core/gif_logic.py`, `cogs/fun/gif.py`, `data/gif_catalogo.json`, 0570 (`gif_privacy`, `gif_blocchi`); `/gif reazione|azione|privacy`.
- r11: D38 `core/moneta_server.py`, `guild_coin_images` (0410), miniatura `moneta.png` in saldo/cassa/giochi/clan info; D30 `MUSIC_TOKEN_6..20`, `MusicFleet.total_workers`, test radio solo owner.
- r10: SPEC §15 `[~]`→`[x]` con le prove già nei test (erano marcatori vecchi del 04/10); ECO-063/065/066/067/068 shop (`shop_repo`, `togli_ruoli_shop_scaduti` nel cog, 0340); LIV-058 (`week_key` in `leveling_activity`); ECO-001/ECO-015 (0341).
- r7 D: `/level premi` (LIV-048/027), `/level pause` (ECO-020), `/level livelli-recenti` (LIV-039, 0203).
- r7 C: #65 M 9.18 tick vocale gilde raggruppato (`apply_ticks`, `clear_activities`, `get_membri_in_gilda`).
- r7 B: NF-12 sfondo immagine (`rank_card_sfondi`, 0202, `prepara_sfondo`, `/level impostazioni card`), NF-40 profilo come immagine (`render_profile_card`).
- r7 A: #144 blocco vocale salvato nel DB (0200, `segna_bloccato`/`togli_blocco`); #127 VOC-007 invita, 008 stato, 011/012 nome da modello e numeri, 015 nascono bloccati, 018 registro (`/gestione voice opzioni`, 0201).
- r5 fun: NF-25 (0120), voci piccole /fun, NF-32 Kick (0121).
- r4: A+B `1ecd983` (0090); giveaway `203a3af` (0091); NF-40 `0319d95` (0092/0093); shop+classifiche (0094/0095). F1 unito `9db9e8a`.

## Cose imparate
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
- GIF: voci senza fonte (dab, salta, canta, supplica, sposa, fragola, rose, arresta, massaggio, ruba, rombo); Klipy/waifu.im senza adattatore; FUN-136 (azioni del server) non fatta.
- Migrazioni r11: 0410. Embed economia non ancora con miniatura: shop, classifiche, daily/work (testo semplice).
- Migrazioni mie: 0090-0095, 0097-0099, 0120-0121, 0200-0203, 0340-0341. NON usare 0096.
- #127 restano VOC-006, 010, 013, 014, 016, 017, 021.
- Colonne `boost_expires_at`/`guild_boost_expires_at` nel database, non usate.
