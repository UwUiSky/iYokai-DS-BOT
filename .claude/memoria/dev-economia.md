# Memoria di dev-economia

## Aggiornata
15/10/2026 · giro r7, ramo `feat/r7liv`, DB `iyokai_wr7liv` (env: `/tmp/claude-0/env_r7liv.sh`), migrazioni 0200–0209. Lavoro PER FILE.

## In corso
- Giro r7 chiuso (4 gruppi su 4). Prossimo giro: altre voci di #124/#125 (reputazione LIV-076…088 come gruppo a parte, classifica settimanale LIV-058, ECO-001 nome della moneta) e #127 (VOC-006, 010, 013, 014, 016, 017, 021).

## Fatto
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

## Aperto
- Migrazioni mie: 0090-0095, 0097-0099, 0120-0121, 0200-0203. NON usare 0096.
- #127 restano VOC-006, 010, 013, 014, 016, 017, 021.
- Colonne `boost_expires_at`/`guild_boost_expires_at` nel database, non usate.
