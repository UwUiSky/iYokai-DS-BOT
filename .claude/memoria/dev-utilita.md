# Memoria di dev-utilita

## Aggiornata
11/10/2026 · ramo feat/66-utility (base 90bbeb2) · G6 chiuso, ramo da pushare

## In corso
- Previsione: 6 gruppi (G1 sticky/benvenuto/programmati/promemoria; G2 role menu; G3 suggerimenti+richieste;
  G4 owner_premium; G5 modules_updated; G6 chiusura). Migrazioni 0027 (ping_ruoli) usata; 0028 libera.
- Giro #66 chiuso (smoke --base 90bbeb2: 420 verdi). Prossimo: `/gestione` (greetings, role_menus), `nonstop-main` -> `/owner radio`, `/report`, `registra_comandi_del_cog` salti `owner`; poi F9 (autoroles, starboard, 10.8/10.14/10.15/10.17) e F13 (scheletri).

## Fatto
- #147 e #67: vedi main. G1 (#66): 10.1/10.3/10.16 già a posto; 10.2, 10.4, 10.5, 10.6 fatti; G2 10.7, G3 10.9, G4 10.12, G5 10.13 fatti (AUDIT_UTILITA.md).

## Cose imparate
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

## Aperto
- - Menu dei ruoli: nessun comando per elencare gli ID dei menu (menu-aggiungi chiede `menu_id` a mano); un elenco richiederebbe un sottocomando in `/gestione ruoli` (controllare il tetto 25).
- Fasi future saltate: 10.8 (F9), 10.11 (F8, già fatto come cerca-comando), 10.14, 10.15, 10.17 (F9); #71 voci Fun non in questi file.
- Scheletri (counters, forms, starboard, birthdays, autoroles, invites, activity_stats, autoresponder, custom_commands, embed_builder): F9/F13.
- Registro dati personali (F5): aggiungere `command_usage`. Menzioni di `/owner` non mostrate nel pannello.
