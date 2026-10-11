# AUDIT_UTILITA.md — cosa non andava in `cogs/utility` e come è stato sistemato

Issue #66 (M 10.x, fase F1). Una riga per problema. Il commit è quello che
chiude la riga; il test è il file che la prova.

| File | Problema | Fix | Commit | Test |
|---|---|---|---|---|
| `cogs/utility/poll.py` | M 10.1: risposta oltre 55 / domanda oltre 300, opzioni a 10 | già fatto in #67 (voci rapide F1) | prima di 90bbeb2 | `tests/test_poll_cog_smoke.py` |
| `cogs/utility/sticky_messages.py` | M 10.3: solo `Forbidden` catturato | già fatto in #67 (`HTTPException`) | prima di 90bbeb2 | `tests/test_sticky_messages_listener.py` |
| `cogs/utility/sticky_messages.py` | M 10.4: dieci messaggi veloci pubblicavano dieci sticky | un blocco per canale intorno a lettura, cancella, invia, salva | G1 | `tests/test_sticky_messages_blocco.py` |
| `cogs/utility/sticky_messages.py` | M 10.6: nessun `allowed_mentions` (un `@everyone` nel testo pingava) | `menzioni_ammesse(ping_ruoli)`; permesso di chi configura salvato in `sticky_messages.ping_ruoli` (0027) | G1 | idem |
| `cogs/utility/sticky_messages.py` | `sticky-set` senza controllo del modulo (gli altri comandi lo hanno) | controllo `is_module_active_for_guild` | G1 | idem |
| `cogs/utility/greetings.py` | M 10.2: testo accettato e poi rifiutato in silenzio; anteprima in errore | lunghezza misurata dopo i segnaposto (`lunghezza_dopo_segnaposto`), `Range` 2000 sull'opzione, `try` e taglio nell'anteprima | G1 | `tests/test_greetings_limiti.py` |
| `cogs/utility/greetings.py` | M 10.6: nessun `allowed_mentions` | ruoli solo con "Menziona tutti" (colonne `*_ping_ruoli`, 0027), `@everyone` mai, utenti solo chi entra/esce | G1 | idem |
| `cogs/utility/greetings.py` | `/gestione benvenuto` senza `dm` azzerava il DM salvato (default `False`) | `dm: bool \| None`, `None` = lascia il valore | G1 | idem |
| `cogs/utility/greetings.py` | addio mandato anche per i bot che escono | `if member.bot: return` | G1 | idem |
| `cogs/utility/greetings.py` | M 10.16 (DM durante un raid) | già fatto in #67 (`raid_in_corso`, `member.bot`) | prima di 90bbeb2 | `tests/test_greetings_ingresso_bot.py` |
| `cogs/utility/scheduled_messages.py` | M 10.5: messaggio non pubblicato senza avviso; testo senza limite; lista oltre 4096 | DM all'autore se canale sparito o invio fallito; `Range[str,1,1800]`; lista con `righe_entro_limite` | G1 | `tests/test_scheduled_messages_limiti.py` |
| `cogs/utility/scheduled_messages.py` | M 10.6: nessun `allowed_mentions` | `payload["ping_ruoli"]` deciso dal permesso dell'autore | G1 | idem |
| `cogs/utility/reminders.py` | M 10.5: testo senza limite, lista oltre 4096 | `Range[str,1,1800]`, `righe_entro_limite` | G1 | idem |
| `cogs/utility/reminders.py` | il canale di ripiego pubblicava il testo dell'utente senza `allowed_mentions` (chiunque poteva far pingare `@everyone` al bot) | solo l'utente stesso menzionabile | G1 | idem |
