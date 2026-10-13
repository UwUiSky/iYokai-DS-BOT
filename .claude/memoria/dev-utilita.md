# Memoria di dev-utilita

## Aggiornata
13/10/2026 · ramo feat/r4-uti (base main 793656c) · lavoro per FILE su #66, #78-#82, #85, #87, #88, #97, #98, #105

## In corso
- Previsione giro r4: 10 gruppi (G1 autoroles NF-07; G2 starboard NF-08; G3 tag NF-09 + prefix 10.15 + risposte NF-10; G4 greetings NF-11; G5 role menu NF-14 + 10.8; G6 embed NF-17; G7 contatori NF-16; G8 compleanni NF-26; G9 inviti NF-27; G10 moduli NF-34). Migrazioni 0080+ (0080 autoroles usata).
- Comandi nuovi: /gestione ruoli auto-*; /moduli starboard|contatori|compleanni; admin: messaggi/comandi. Tabelle nuove vanno in core/data_registry.py (test_data_registry).
- Prossimo: G3b autoresponder NF-10 (0083, comandi `/admin comandi risposta-crea|risposta-elimina|risposte`), poi G4 greetings NF-11.

## Fatto
- r4 G1 NF-07 autoroles (0080); G2 NF-08 starboard (0081); G3a NF-09 tag + M10.15 (0082, /admin comandi crea|modifica|elimina|elenco|prefisso, /utility tag; prefix = guild_config.prefix): commit nel log.
- #71 F1: 15.1 (defer + Range 1-100) e 15.2 (cache 24h, allegato, credito, pausa 10s) in cogs/fun/entertainment.py + core/image_search_fetcher.py; resto di §15 non esiste in F1.
- #147 e #67: vedi main. G1 (#66): 10.1/10.3/10.16 già a posto; 10.2, 10.4, 10.5, 10.6 fatti; G2 10.7, G3 10.9, G4 10.12, G5 10.13 fatti (AUDIT_UTILITA.md).

## Cose imparate
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
