# Memoria di dev-economia

## Aggiornata
15/10/2026 · giro r7, ramo `feat/r7liv`, DB `iyokai_wr7liv` (env: `/tmp/claude-0/env_r7liv.sh`), migrazioni 0200–0209. Lavoro PER FILE.

## In corso
- Previsione r7: 4 gruppi, poi stop. A vocali (#144 residuo, #127) FATTO. B NF-12 sfondo immagine rank card (#83) + NF-40 profilo come immagine (#111). C #65 M 9.18 (PERF-4 nel worker vocale delle gilde). D catalogo #124/#125 voci piccole (annunci level-up filtrati LIV-035/036/037, elenco ruoli premio LIV-048, ...).
- Prossimo passo: B, `core/rank_card_image.py` (sfondo da byte salvati nel DB, migrazione 0202).

## Fatto
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
- Output dei test lunghi: `-p no:warnings` e log nella scratchpad; il traceback di birthdays a fine run è rumore.

## Aperto
- Migrazioni mie: 0090-0095, 0097-0099, 0120-0121, 0200-0201. NON usare 0096.
- `core/guild_clan_voice_worker.py`: ~6 query per utente a ogni tick (PERF-4, M 9.18).
- `rank_card_prefs` (user_id) non è nel flusso GDPR di cancellazione.
- #127 restano VOC-006, 010, 013, 014, 016, 017, 021.
- Colonne `boost_expires_at`/`guild_boost_expires_at` nel database, non usate.
