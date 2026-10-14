# Memoria di dev-utilita

## Aggiornata
14/10/2026 · ramo feat/r5-fun (base main a5f4e30) · lavoro per FILE: #71, #131, #96, #130, #103, #129

## In corso
- Previsione r5: 5 gruppi. G1 #71+#131 fun (fatto); G2 NF-25 #96 + #130 (0120); G3 NF-32 #103 Kick/ruolo live/guida social (0121); G4 #129 voci feed; poi COMMAND_LIST+SPEC+push+rapporto.
- Migrazioni da 0120. Registro dati (core/data_registry.py) per ogni tabella nuova.

## Fatto
- r4: G1-G10 (autorole, starboard, tag, autoresponder, greetings, role menu, embed, contatori, compleanni, inviti, moduli): vedi git log.
- r5 G1: #71 (15.1/15.2 già in main) + #131 voci piccole: cogs/fun/fun_extra.py (/fun scegli|numero|testo|casuale|scherzo|effetto), dice formula, joke tema, fact animale, 8ball/meme con Range e senza menzioni.

## Cose imparate
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
- - Menu dei ruoli: nessun comando per elencare gli ID dei menu (menu-aggiungi chiede `menu_id` a mano); un elenco richiederebbe un sottocomando in `/gestione ruoli` (controllare il tetto 25).
- Fasi future saltate: 10.8 (F9), 10.11 (F8, già fatto come cerca-comando), 10.14, 10.15, 10.17 (F9).
- Scheletri (counters, forms, starboard, birthdays, autoroles, invites, activity_stats, autoresponder, custom_commands, embed_builder): F9/F13.
- Registro dati personali (F5): aggiungere `command_usage`. Menzioni di `/owner` non mostrate nel pannello.

## Round r4 (vecchio)
- Fatti G1-G9 (autorole, starboard, tag, autoresponder, welcome image, role menu modi, embed, counters, compleanni, inviti 0089). Prossimo: G10 forms (0090 è di altri: usare 0089+... controllare il numero libero), poi COMMAND_LIST, SPEC, push, rapporto.
- Inviti: usare solo invite_tracker.resolve_join_invite; dataclass senza @property (il test callers li segnala).
- G10 forms fatto (0091). COMMAND_LIST e SPEC aggiornati. Resta: commit, push, rapporto. Autoresponder 14.7 lasciato [ ] (niente wildcard/condizioni).
