# Memoria dev-moderazione
## Aggiornata
2026-11-08, giro r18automod (ramo feat/r18automod, wt /home/claude/wt/r18automod, DB iyokai_w18am, migr. 0509 e da 0533). Smoke da fare.
## In corso
r18automod chiuso: A10 (calore, AMD-068/069/072), A11 (pulizia, 0509, AMD-073/074), AMD-008 (soglia_canale), finestra Innesco con ruoli/casi. Blocco AutoMod #116 finito. Prossimo: merge e prova live; poi F7 (/mod, /modban). r17mod: MOD-102 (cogs/automod) ora sbloccato dopo il merge di r17automod. main.py deve usare core.automod_eventi.chiede_intent_presenze() (non mio).
Comando: DATABASE_URL=postgresql://postgres:testpass@127.0.0.1:5432/iyokai_w18am in ogni comando (mai iyokai_test). Testi: scratchpad/r18am_addt.py file.json (dict chiave -> [it, en]).
## Fatto
- r18 A10/AMD-008/finestra: core/automod_calore_logic.py (Termometro, CanaliFermi, punti, azioni_calore), CaloreConfig in AutomodAdvancedConfig (JSON), core/automod_calore_opzioni.py, /admin-automod calore, AutomodCog._scalda e _innesco_messaggio (soglia_canale); core/automod_innesco_logic.py (filtro ruoli/casi, soglia); finestra Innesco con 5o campo. test_automod_calore(_logic), _soglia_canale, _innesco_logic, _regole_pannello. Smoke da fare
- r18 A11: migr. 0509 automod_pulizie, repo, core/automod_pulizia_logic.py, automod_pulizia.py (un giro), automod_pulizia_service.py, cogs/automod/pulizia.py (ciclo 5 min, /admin-automod pulizia, on_guild_channel_delete), data_registry. test_automod_pulizia(_logic/_servizio/_cog). Smoke da fare
- r17 A9 eventi non-messaggio (core/automod_eventi*.py, caso_eventi.py, cogs/automod/eventi.py) e D67 account rubato (core/account_rubato*.py). r17 M4/M5/M7 moderazione (vocale, motivi, canali). Smoke da fare
- r15-r16: A1-A8 AutoMod (regole, azioni, contatori, pannello, liste, decisioni; migr. 0500-0503), verifica D64/D65/D67 (VPN, blocchi, IP; 0507/0508/0530/0531), R14 paese 0490.
- Giri G1-G7, R5-R11 (git log e REGISTRO_RISOLTE): tempban, appelli, verify, lockdown, phishing, captcha, anti-raid, odio D35 e altro.
## Cose imparate
- Test con tanti messaggi finti: MagicMock(spec=discord.Message), non fake_message (autospec: centinaia di istanze = minuti)
- Pulizia canali: giro segnato su DB PRIMA di cancellare (riserva_dovute); 3x 403 spengono la riga; blocco solo < 13,9 giorni, singoli <= 100
- Calore: stato in memoria (BoundedCache), calo calcolato in lettura; regola con calore 0 non scalda; solo messaggi
- Modale Innesco: ricostruisce l'innesco dai campi, quindi conserva a mano numero/secondi/limite
- Anti-giri-a-vuoto (A9): esegui_azioni segna in automod_eventi_logic.effetti ruolo/nome/uscita PRIMA di agire; casi con origine automod ignorati; thread creati dal bot ignorati (e_un_nostro_bot sull'autore)
- Testi: locales/it e en-US testi.json, riga in coda (no json.dump); un test che mette un'opzione nuova letta da db va patchato (db non connesso nei test di cog)
- Scadenze IP (verify_ip): il ban vince sempre (on_member_remove arriva anche dopo il ban); kick riconosciuto dal registro audit, senza permesso = uscita volontaria; log IP: mai exc_info, solo type(errore)
- data_registry: test_riferimenti_comandi legge anche le note: mai «/privacy», scrivere «/utility privacy cancella»
- Sostituendo un blocco di codice con slice (index..index) controlla cosa c'e' in mezzo: ho cancellato riepilogo/azzera (lo ha trovato test_repository_callers)
- Regole AutoMod: azioni vecchie (delete,warn,mute,kick,ban) -> azioni_dai_nomi_vecchi (ordine di prima); actions-set/mute-duration scrivono anche via servizio (doppia scrittura fino ad A4)
- Verifica web: i segnali delle intestazioni si ignorano se il socket e' privato o proxy fidato (reverse proxy non dichiarato bloccherebbe tutti); IP non globali mai bloccati (is_global)
- Locales comandi.json: mai riscrivere con json.dump (chiavi ordinate/escape): inserire la riga di testo
- CSP del pannello: script solo su /verifica/ (CSP_VERIFICA); resto default-src none
- Chiavi guild nuove con tipo nuovo: CONTROLLI_PER_TIPO in config_history; i campi in SCHEDE di core/config_impostazioni.py (pannello)
- D15: Mod non ha listener; azioni di sicurezza via bot_roles; e_un_nostro_bot per "e' il bot"
- discord.RateLimited NON e' HTTPException: va preso a parte
- Tabelle sicurezza e verify in run_migrations dei repo; config anti-raid/anti-nuke in JSON: campi nuovi senza migrazione
- Colonne nuove su tabelle dei repo: migrazione numerata (gira dopo i repo). Tabella nuova: anche in core/data_registry.py
- Smoke e suite oltre 2 min: run_in_background su log in scratchpad (grep sul log, mai pipe con tail nel foreground)
- Il bot non puo' scrivere a un bannato/espulso: DM prima, cancellato se l'azione fallisce
- Stato su DB PRIMA dell'azione irreversibile; job di scadenza protetti con controllo nell'handler
- Opzione facoltativa nuova: va DOPO le obbligatorie (test che chiamano callback per posizione)
- test_riferimenti_comandi legge anche docstring e messaggi: citare il percorso intero
- Nuove chiavi guild settings: SETTINGS_SCHEMA + CONTROLLI_PER_TIPO + tests/test_config_import_validation.py; chi-puo'-cosa anche CHIAVI_SOLO_PROPRIETARIO
- Comando nuovo: ATTESI in test_f7_moderazione_gruppi e locales/comandi.en.json (nome e descrizione)
- Ogni modulo in cogs/ ha setup(): codice senza cog va in core/ (test_command_tree_invariants lo controlla)
- Tabelle senza chiamante in produzione = cricchetto di test_repository_callers: meglio cancellare il metodo
- normalizza() del filtro legge "!" come i: per le chiavi di cache usare parole+casefold, non normalizza
- Test del cog automod: db finto passato come `archivio` alle funzioni (mai db._pool); libreria_odio va finta (AsyncMock) senza pool
- Str.replace sostituisce TUTTE le occorrenze; con piu' decorator uguali cercare l'indice dopo il nome del comando
## Aperto
- M5: _prepara_massa ora dà (ids, motivo); nel DM il nome locale del messaggio inviato e' dm_inviato (il parametro dm del comando e' un bool)
- M5: durata nel motivo pronto non fatta (decidere)
- Cog nuovo in cogs/moderation: aggiungerlo a MODULI di tests/test_f7_moderazione_gruppi.py oltre ad ATTESI, e il testo en dei comandi in locales/en-US/comandi.json
- D67: verify_blocchi ha UNA riga per persona (PK user_id): con account limitato in piu' server il ticket si apre solo nell'ultimo; per tutti serve cambiare PK (migr. 0531) e cogs/tickets/modmail.py (non mio, in revisione r16ticket)
- Codice con View/Modal senza cog va in core/ (ogni file in cogs/ vuole setup())
- AMD-018 (stato/attivita) non fatto: serve intent Presenze, decide l'owner
- decide_staff (A8, 0503) non ancora: l'azione e' nel JSON ma il motore la ignora
- Test con _FakeMessage senza webhook_id: nel cog usare sempre getattr per gli attributi nuovi
- D67: chiave VERIFY_IP_ENCRYPTION_KEY da mettere nel .env di produzione (senza, nessun IP salvato); i listener di scadenza IP girano anche a modulo Verify spento
- D64: Tor/reti da aggiornare a mano con scripts/aggiorna_vpn.py (nessun job); licenza elenco Tor da confermare
- MOD-065 (motivo facoltativo): cambia la firma di tutti i comandi
- #119 LOG-029; #113 log via webhook; OAuth rientro oltre 7 giorni; alt_detection (#92)
- Eccezioni allow_list anti-invito: tetto 25 voci = 8 inviti
- SIC-045, AMD-067, SIC-016/021
- data_registry (dev-core): scheduled_actions con channel_unlock usa user_id = ID del canale
- D35: pagina /proprietario per la libreria (dev-web); le candidate valgono solo nei server che le hanno segnalate
