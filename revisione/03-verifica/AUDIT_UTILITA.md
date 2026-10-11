# AUDIT_UTILITA.md — cosa non andava in `cogs/utility` e come è stato sistemato

Issue #66 (M 10.x, fase F1). Una riga per problema. Il commit è quello che
chiude la riga; il test è il file che la prova.

| File | Problema | Fix | Commit | Test |
|---|---|---|---|---|
| `cogs/utility/poll.py` | M 10.1: risposta oltre 55 / domanda oltre 300, opzioni a 10 | già fatto in #67 (voci rapide F1) | in main (#67) | `tests/test_poll_cog_smoke.py` |
| `cogs/utility/sticky_messages.py` | M 10.3: solo `Forbidden` catturato | già fatto in #67 (`HTTPException`) | in main (#67) | `tests/test_sticky_messages_listener.py` |
| `cogs/utility/sticky_messages.py` | M 10.4: dieci messaggi veloci pubblicavano dieci sticky | un blocco per canale intorno a lettura, cancella, invia, salva | b0cecf3 | `tests/test_sticky_messages_blocco.py` |
| `cogs/utility/sticky_messages.py` | M 10.6: nessun `allowed_mentions` (un `@everyone` nel testo pingava) | `menzioni_ammesse(ping_ruoli)`; permesso di chi configura salvato in `sticky_messages.ping_ruoli` (0027) | b0cecf3 | idem |
| `cogs/utility/sticky_messages.py` | `sticky-set` senza controllo del modulo (gli altri comandi lo hanno) | controllo `is_module_active_for_guild` | b0cecf3 | idem |
| `cogs/utility/greetings.py` | M 10.2: testo accettato e poi rifiutato in silenzio; anteprima in errore | lunghezza misurata dopo i segnaposto (`lunghezza_dopo_segnaposto`), `Range` 2000 sull'opzione, `try` e taglio nell'anteprima | b0cecf3 | `tests/test_greetings_limiti.py` |
| `cogs/utility/greetings.py` | M 10.6: nessun `allowed_mentions` | ruoli solo con "Menziona tutti" (colonne `*_ping_ruoli`, 0027), `@everyone` mai, utenti solo chi entra/esce | b0cecf3 | idem |
| `cogs/utility/greetings.py` | `/gestione benvenuto` senza `dm` azzerava il DM salvato (default `False`) | `dm: bool \| None`, `None` = lascia il valore | b0cecf3 | idem |
| `cogs/utility/greetings.py` | addio mandato anche per i bot che escono | `if member.bot: return` | b0cecf3 | idem |
| `cogs/utility/greetings.py` | M 10.16 (DM durante un raid) | già fatto in #67 (`raid_in_corso`, `member.bot`) | in main (#67) | `tests/test_greetings_ingresso_bot.py` |
| `cogs/utility/scheduled_messages.py` | M 10.5: messaggio non pubblicato senza avviso; testo senza limite; lista oltre 4096 | DM all'autore se canale sparito o invio fallito; `Range[str,1,1800]`; lista con `righe_entro_limite` | b0cecf3 | `tests/test_scheduled_messages_limiti.py` |
| `cogs/utility/scheduled_messages.py` | M 10.6: nessun `allowed_mentions` | `payload["ping_ruoli"]` deciso dal permesso dell'autore | b0cecf3 | idem |
| `cogs/utility/reminders.py` | M 10.5: testo senza limite, lista oltre 4096 | `Range[str,1,1800]`, `righe_entro_limite` | b0cecf3 | idem |
| `cogs/utility/reminders.py` | il canale di ripiego pubblicava il testo dell'utente senza `allowed_mentions` (chiunque poteva far pingare `@everyone` al bot) | solo l'utente stesso menzionabile | b0cecf3 | idem |
| `cogs/utility/role_menus.py` | M 10.7: titolo, descrizione, etichetta senza limite | `Range` 256 / 2000 / 80 sulle opzioni | 8b72e27 | `tests/test_role_menus_limiti.py` |
| `cogs/utility/role_menus.py` | emoji accettata qualunque stringa | `valida_emoji` (unicode, tasto, personalizzata) + emoji personalizzata che il bot vede | 8b72e27 | idem |
| `cogs/utility/role_menus.py` | campo dell'embed oltre 1024 con 25 etichette lunghe: la modifica falliva ma l'admin leggeva "Opzione aggiunta" | elenco su più campi (`dividi_in_pagine`), tetto 6000 | 8b72e27 | idem |
| `cogs/utility/role_menus.py` | opzione salvata nel database prima di pubblicare, errore ingoiato | `_pubblica_menu` prima, `add_option` dopo; se Discord rifiuta l'admin lo legge e nulla è salvato | 8b72e27 | idem |
| `cogs/utility/role_menus.py` | togliere l'ultima opzione lasciava una tendina vuota (non valida) | menu e messaggio eliminati, l'admin lo sa | 8b72e27 | idem |
| `cogs/utility/role_menus.py` | `toggle=False` ignorato dal bottone | il bottone non toglie il ruolo, risponde "già" | 8b72e27 | idem |
| `cogs/utility/role_menus.py` | messaggio del menu cancellato a mano: ogni modifica falliva in silenzio | ripubblicato al posto di quello sparito | 8b72e27 | idem |
| `cogs/utility/role_menus.py` | solo `Forbidden` catturato in bottone, tendina e reazioni | `HTTPException` con risposta all'utente | 8b72e27 | idem |
| `cogs/utility/role_menus.py` | all'avvio un menu rimasto senza opzioni registrava una View vuota | saltato | 8b72e27 | idem |
| `cogs/utility/suggestions.py` + `core/repositories/suggestion_repo.py` | M 10.9: due staff che decidono insieme sovrascrivevano la decisione (leggi poi scrivi) | `set_status` = `UPDATE … WHERE status = 'pending' RETURNING`; chi perde legge "già deciso" | 8c35cc3 | `tests/test_suggestions_limiti.py` |
| `cogs/utility/suggestions.py` | `/suggest` lavorava (salva, pubblica, reagisce) prima di rispondere; testo senza limite (embed 4096) | `defer()` e followup; `Range[str,1,2000]` | 8c35cc3 | idem |
| `cogs/utility/suggestions.py` | invio fallito (non solo `Forbidden`) lasciava una riga senza messaggio, con eccezione non gestita | `HTTPException` gestita, riga cancellata, l'utente lo sa | 8c35cc3 | idem |
| `cogs/utility/custom_command_requests.py` + repo | stessa decisione non atomica; pubblicazione prima di rispondere; richiesta "salvata" ma mai visibile se l'invio falliva | `set_status` atomico, `defer()`, riga cancellata se l'invio fallisce; DM al richiedente senza menzioni | 8c35cc3 | idem |
| `cogs/utility/owner_premium.py` | M 10.12: `premium-list` a 1759/2000 con 32 moduli (altri 4 la rompono); liste whitelist e blacklist oltre 2000; `subscriptions` e `status-all` senza tetto o tagliati | `invia_a_pagine` (`cogs/utility/_owner_pagine.py`): una pagina o bottoni Indietro/Avanti, solo owner | 8782ee6 | `tests/test_owner_premium_limiti.py` |
| `cogs/utility/owner_premium.py` | pannello premium con più di 25 moduli: tendina non valida, embed oltre 25 campi | 25 moduli per pagina con Indietro/Avanti; nomi tagliati a 100/256 | 8782ee6 | idem |
| `cogs/utility/owner_premium.py` | `eval`, `shell` e `announce` senza limite (embed 4096) | `Range[str,1,4000]` | 8782ee6 | idem |
| `cogs/utility/setup.py`, `cogs/utility/config_history.py` | M 10.13: `modules_updated` partiva solo dal salvataggio di `/admin setup attiva` (il wizard, l'import, il reset e il rollback cambiavano i moduli in silenzio) | wizard: evento per modulo cambiato; import, reset e rollback: stato dei moduli prima/dopo e evento per i soli cambiati (`core/modules_updated_logic.py`) | caa7a42 | `tests/test_modules_updated.py` |
