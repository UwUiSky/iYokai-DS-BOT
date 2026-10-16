# Memoria di dev-utilita

## Aggiornata
16/10/2026 · ramo feat/r8uti (worktree /home/claude/wt/r8uti, env /tmp/claude-0/env_r8uti.sh, DB iyokai_wr8uti) · #123, #128, #66, #82

## In corso
- Previsione r8: 4 gruppi. G1 nuovo gruppo `/ruoli` (D25, /gestione a 6122) con dai/togli/temporaneo, azzera, massa, massa-ferma, crea, modifica, diagnosi, scelta (RUO-042/043/092/094-109/113; 0231 self_roles). G2 `/utility ruolo` (RUO-090/091/093) + `/utility scheda` (UTL-195/197-200/202, RUO-110-112). G3 condizioni ruoli automatici RUO-034/035/036/038 (0230). G4 se resta: suggerimenti UTL-135..138. Poi COMMAND_LIST, SPEC, VERIFICA_LIVE, REGISTRO, rapporto.
- Migrazioni riservate 0230-0239. Pesi: moduli 6429 (pieno), gestione 6122, utility 4492 (18 figli).

## Fatto
- r8 G1 c265011: /ruoli (D25 quinto caso) cogs/utility/ruoli_strumenti.py + core/ruoli_strumenti_logic.py + self_role_repo (0231); /utility ruolo.
- r8 G2 417817c: /utility scheda (cogs/utility/schede.py, core/schede_logic.py).
- r8 G3: ruoli automatici con solo_con/non_con/ridai_se_tolto e auto-sincronizza (0230); ruoli a tempo di /ruoli non ricordati.
- r8 G4: suggerimenti con in valutazione/realizzato, motivo in finestra, DM, canale dei decisi (0232).
- r4: G1-G10 (autorole, starboard, tag, autoresponder, greetings, role menu, embed, contatori, compleanni, inviti, moduli): vedi git log.
- r5 G1: #71 (15.1/15.2 già in main) + #131 voci piccole: cogs/fun/fun_extra.py (/fun scegli|numero|testo|casuale|scherzo|effetto), dice formula, joke tema, fact animale, 8ball/meme con Range e senza menzioni.
- r5 G2: NF-25 attività (0120): activity_stats.py (raccolta+ruoli, /moduli statistiche …), server_stats.py (viste, bottoni), repo+logic; member_total per giveaway.

## Cose imparate
- Scratchpad condivisa con altri agenti: file con prefisso `uti_`. Pesi gruppi: scratchpad/uti_pesi.py. Traduzioni: scratchpad/tradu.py (tiene il formato indent=1 del json).
- pytest raccoglie le funzioni importate che iniziano per `test`: niente nomi `testo_*`/`test*` nelle funzioni di logica importate dai test.
- Role menu: `_applica(guild, member, decisione, motivo)` e `decidi_azione/decidi_selezione` (core/role_menu_logic) sono l'unico punto che da/toglie ruoli; pass guild esplicito (i fake non hanno member.guild).
- smoke --base main diventa lento (2-3 min) con più gruppi: lanciarlo con timeout 600000.
- Tabelle nuove: .sql in core/migrations + voce in core/data_registry.py (Scadenza per i dati a tempo). Comandi: `@comando_di_gruppo("gestione"/"moduli"/"admin", sottogruppo=(nome, descr))`; autocomplete admin = `autocomplete_protetto(Livello.ADMIN)`; test albero: `await modulo.setup(Bot)` poi `comando_nel_gruppo("gruppo", "sotto cmd")`.
- Ping nei testi admin: `core/admin_mentions_logic.py` (menzioni_ammesse, puo_pingare_ruoli); il permesso si salva a configurazione.
- Elenchi che crescono: `core/lista_limiti_logic.py` (righe_entro_limite per embed, dividi_in_pagine per messaggi).
- Handler dello scheduler: se rilancia l'errore l'azione viene ritentata; per errori permanenti avvisare l'autore e non rilanciare.
- Fake dei test: `send(content, **kwargs)` per accettare `allowed_mentions`.
- Role menu: pubblicare PRIMA (`_pubblica_menu` con l'elenco futuro), salvare DOPO; `valida_emoji` in core/role_menu_logic.
- Decisioni staff (suggerimenti, richieste): `UPDATE … WHERE status='pending' RETURNING`, mai leggi-poi-scrivi.
- Elenchi dell'owner: `invia_a_pagine` (cogs/utility/_owner_pagine.py); in una vista con decoratori i bottoni sono children prima del Select aggiunto in __init__.
- `modules_updated`: da ogni percorso che cambia i moduli; per operazioni in blocco confrontare lo stato prima/dopo (core/modules_updated_logic.py). Nei test non chiamare un modulo `setup_module` (pytest lo prende per hook).
- Dopo la revisione: un blocco (lock) per risorsa anche per set/remove; pubblicazione = reazioni prima dell'edit; ping D12: `utente_puo_pingare_ruoli` unica; liste owner riusano cogs/leveling/_pagine.
- Registro: i comandi di gruppo si provano con `cog.metodo.callback(cog, interaction, ...)`; limiti con `comando_nel_gruppo(...).to_dict(bot.tree)`.
(vedi sotto: le trappole di #147/#67 restano valide)
- Lo stato (last_seen, last_known_live) avanza solo dopo `send` riuscito; ETag solo se nulla da ritentare.
- `@comando_di_gruppo` va sopra describe/choices; il permesso lo dà il gruppo.
- `registra_comandi_del_cog` mette anche `owner` nell'albero globale: i cog owner fanno `tree.remove_command("owner")` in cog_load.
- test_command_policy: ogni comando di primo livello nuovo va in AUDIENCE (tests/support/command_policy.py).
- `core/cog_manager` carica ogni .py di cogs/ come cog: un file di sole classi UI si chiama `_nome.py`.
- `test_repository_callers`: ogni metodo di repo deve avere un chiamante di produzione.
- `COMMAND_LIST.md` va rigenerato (scripts/generate_command_list.py) quando cambia l'albero.

- Fun/Pixabay: la cache è in memoria (si perde al riavvio); `Range[...]` in get_type_hints è un oggetto con min_value/max_value; ComandoDiGruppo: usare `.callback`.

## Aperto
- Condivisione macchina: NON usare /tmp/claude-0/env.sh (lo riscrivono altri agenti): uso env_r5fun.sh. Giveaway: passare il requisito messaggi a activity_stats_repo.member_total (cogs/leveling non mio).
- - Menu dei ruoli: nessun comando per elencare gli ID dei menu (menu-aggiungi chiede `menu_id` a mano); un elenco richiederebbe un sottocomando in `/gestione ruoli` (controllare il tetto 25).
- Fasi future saltate: 10.8 (F9), 10.11 (F8, già fatto come cerca-comando), 10.14, 10.15, 10.17 (F9).
- Scheletri (counters, forms, starboard, birthdays, autoroles, invites, activity_stats, autoresponder, custom_commands, embed_builder): F9/F13.
- Registro dati personali (F5): aggiungere `command_usage`. Menzioni di `/owner` non mostrate nel pannello.

## Round r4 (vecchio)
- Fatti G1-G9 (autorole, starboard, tag, autoresponder, welcome image, role menu modi, embed, counters, compleanni, inviti 0089). Prossimo: G10 forms (0090 è di altri: usare 0089+... controllare il numero libero), poi COMMAND_LIST, SPEC, push, rapporto.
- Inviti: usare solo invite_tracker.resolve_join_invite; dataclass senza @property (il test callers li segnala).
- G10 forms fatto (0091). COMMAND_LIST e SPEC aggiornati. Resta: commit, push, rapporto. Autoresponder 14.7 lasciato [ ] (niente wildcard/condizioni).
