# Memoria di dev-economia

## Aggiornata
27/10/2026 · giro r10, ramo `feat/r10liv`, DB `iyokai_wr10liv`, migrazioni 0340–0349 (usate 0340, 0341). Lavoro PER FILE.

## In corso
- Giro r10: le 20 voci `[~]` di SPEC §15 sono chiuse. Fatti shop (0340), classifica settimanale, nome moneta e tassa/tetto su pay (0341).
- Prossimo giro: reputazione LIV-076…088 (gruppo a parte), #127 (VOC-006, 010, 013, 014, 016, 017, 021), altre voci di #124/#125 (ECO-003 tetto saldo, ECO-007 storico personale, ECO-026 premi settimanale/mensile, LIV-044/045 ruoli per classifica).

## Fatto
- r10: SPEC §15 `[~]`→`[x]` con le prove già nei test (erano marcatori vecchi del 04/10); ECO-063/065/066/067/068 shop (`shop_repo`, `togli_ruoli_shop_scaduti` nel cog, 0340); LIV-058 (`week_key` in `leveling_activity`); ECO-001/ECO-015 (0341).
- r7 D: `/level premi` (LIV-048/027), `/level pause` (ECO-020), `/level livelli-recenti` (LIV-039, 0203).
- r7 C: #65 M 9.18 tick vocale gilde raggruppato (`apply_ticks`, `clear_activities`, `get_membri_in_gilda`).
- r7 B: NF-12 sfondo immagine (`rank_card_sfondi`, 0202, `prepara_sfondo`, `/level impostazioni card`), NF-40 profilo come immagine (`render_profile_card`).
- r7 A: #144 blocco vocale salvato nel DB (0200, `segna_bloccato`/`togli_blocco`); #127 VOC-007 invita, 008 stato, 011/012 nome da modello e numeri, 015 nascono bloccati, 018 registro (`/gestione voice opzioni`, 0201).
- r5 fun: NF-25 (0120), voci piccole /fun, NF-32 Kick (0121).
- r4: A+B `1ecd983` (0090); giveaway `203a3af` (0091); NF-40 `0319d95` (0092/0093); shop+classifiche (0094/0095). F1 unito `9db9e8a`.

## Cose imparate
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

## Aperto
- Migrazioni mie: 0090-0095, 0097-0099, 0120-0121, 0200-0203, 0340-0341. NON usare 0096.
- #127 restano VOC-006, 010, 013, 014, 016, 017, 021.
- Colonne `boost_expires_at`/`guild_boost_expires_at` nel database, non usate.
