# Memoria dev-moderazione
## Aggiornata
2026-11-23 sera, giro r3mod (ramo feat/r3mod, wt /home/user/wt-115, DB iyokai_w115; migr. 0930; restano 0931-0939): mute a ruolo come gradino della scala e shadowban (D127, D128). Smoke da fare.
(prima) 2026-11-23, giro r1rete (wt /home/user/wt-net, DB iyokai_wnet; migr. 0820): AMD-030 link (commit db4e8179) e VER-025 rete tra server. Smoke da fare. Migrazioni libere: 0821-0829.

## In corso
Giro r3mod finito. Dopo il merge: smoke (test_f7_moderazione_gruppi, test_command_tree_invariants, test_i18n_completo, test_moderation_shadowban, test_moderation_mute_scala), cacciatore-bug, revisore-capo, prova su Discord (VERIFICA_LIVE MOD-SHADOW, MOD-MUTE-SCALA). Idea non fatta: shadowban come gradino della scala.
## Fatto
- r3mod: gradino `mute` della scala (core/moderation_mute_azione.py, escalation.py); shadowban (core/moderation_shadowban.py, cogs/moderation/shadowban.py, 0930, XP e statistiche escluse); test_moderation_shadowban, test_moderation_mute_scala
- r3automod: core/automod_avviso.py (DM con le regole, canale 8 s se DM chiusi, tetto 30 s e 5 in 10 min, /admin-automod avviso, chiavi automod_avviso_attivo/testo); core/moderazione_traduci.py (bottone persistente iyokai:modtraduci, `traducibile(guild, **kw)`, testi del bot o snodo AI) + cogs/moderation/traduci.py; test_automod_avviso, test_moderazione_traduci
- r2mod parte 3: MOD-016 (0804), MOD-091/092/094/095/096 (0803), MOD-103/104 (0805), MOD-051 (0806), MOD-053, AMD-031
- r2mod parte 2: CFG-024+VER-018 (permessi per azione, 0802), MOD-034 tempban, MOD-040, MOD-060, AMD-057/071 (core/automod_emergenza.py), VER-002/003/006/007/023/028
- r2mod: MOD-008/063 (appelli: senza appello, timeout; 0800), MOD-018/019 (ruolo mute), MOD-033/035 (scala con finestra; 0801), MOD-093/097 (blocco a tempo e stato), UTL-204 (esporta-chat), UTL-205 (snipe utente); segni nei test per MOD-020/032/052/061/062/109/111, VER-001/004/005/021/022/024/026
- r15-r19 (git log, REGISTRO_RISOLTE): moderation_conferma/risposte/ricerca/prove, motivi preimpostati (D68), moderation_dm, scheda e segnalazioni, opzioni M5/M7, eventi A9, AutoMod A1-A8, verifica VPN/IP
- r15-r19 (git log, REGISTRO_RISOLTE): moderation_conferma/risposte/ricerca/prove, motivi preimpostati (D68), moderation_dm, scheda e segnalazioni, opzioni M5/M7, eventi A9, AutoMod A1-A8, verifica VPN/IP
- r15-r19 (git log, REGISTRO_RISOLTE): moderation_conferma/risposte/ricerca/prove, motivi preimpostati (D68), moderation_dm, scheda e segnalazioni, opzioni M5/M7, eventi A9, AutoMod A1-A8, verifica VPN/IP
- r15-r19 (git log, REGISTRO_RISOLTE): moderation_conferma/risposte/ricerca/prove, motivi preimpostati (D68), moderation_dm, scheda e segnalazioni, opzioni M5/M7, eventi A9, AutoMod A1-A8, verifica VPN/IP
- r15-r19 (git log, REGISTRO_RISOLTE): moderation_conferma/risposte/ricerca/prove, motivi preimpostati (D68), moderation_dm, scheda e segnalazioni, opzioni M5/M7, eventi A9, AutoMod A1-A8, verifica VPN/IP
## Cose imparate
- Test con fake_role: is_default() e' vero solo per id 0, quindi @everyone finto = fake_role(0); i canali finti vogliono .guild e overwrites_for/set_permissions a mano; guild.get_member va registrato o check_can_moderate dice «non riesco a verificare»
- Cog con CogConGruppi: se sovrascrivi cog_load/cog_unload chiama super(), altrimenti i comandi non entrano nell'albero
- Config e` frozen: nei test l'OWNER_ID e` quello di conftest (123456789); i test non scaricano liste (LINK_LISTE_ATTIVE=nessuna in conftest)
- Metodi di repo senza chiamante in produzione rompono test_repository_callers; stringhe «/qualcosa» nel codice sono lette da test_riferimenti_comandi
- Chiavi guild nuove: aggiungi tipo in config_history (SETTINGS_SCHEMA + CONTROLLI_PER_TIPO) e un valore in SETTINGS_VALIDE di test_config_import_validation; descrizioni di opzioni e comandi entro 95 caratteri
- Nei test fake_member(1) e' il proprietario (owner_id=1): usa altri id per chi deve essere sanzionato
- Locales: json.dumps(ensure_ascii=False, indent=2 testi / 1 comandi)+newline riscrive il file identico: si puo' usare; i comandi in en-US vanno in `descrizioni` (percorso intero) e `nomi` (nome singolo)
- Un comando nuovo: aggiungilo agli ATTESI di test_f7_moderazione_gruppi; `$3 - INTERVAL` in asyncpg vuole il cast ::timestamptz
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
- Migrazioni: girano in ordine di numero: un ALTER su una tabella creata da 0512 deve avere numero maggiore (0532, non 0511)
- Sostituire un blocco con slice: ancorare sul sottogruppo (SOTTOGRUPPO_MOTIVI), mai sul solo nome=«aggiungi» (ce ne sono due): ho cancellato 3 comandi e l'ha visto test_f7
- Un comando che esegue un altro comando (applica, tasti scheda) deve ricontrollare il livello: /mod-sanzioni e /mod-ban hanno livelli diversi (D2)
- Test che chiamano il callback di un cog: get_member deve conoscere sia il moderatore sia il bersaglio (side_effect per id), se no «su te stesso»
- Il DM delle sanzioni legge le opzioni dal db: i test dei cog senza db vanno patchati (core.moderation_dm.costruisci)
## Aperto
- r3automod: l'avviso si salta se la regola ha gia' mandato dm/warn/kick/ban/avviso_canale (scelta mia, D110); il bottone Traduci riconosce i testi fissi solo per testo esatto o modello; i motivi misti (testo fisso + dati) vanno all'AI
- re2 non ha re2.IGNORECASE: usare il prefisso (?i). Comando che deve continuare dopo una conferma: ritorna l'interazione del tasto e il comando sostituisce `interaction` (la prima e` gia` risposta)
- Mai lanciare pytest di altri file sullo stesso DB mentre ne gira uno in background: e anche modificare cog durante la run falsa i test dell'albero comandi
- M5: _prepara_massa dà (ids, motivo); nel DM il nome locale del messaggio inviato è dm_inviato (il parametro dm del comando è un bool)
