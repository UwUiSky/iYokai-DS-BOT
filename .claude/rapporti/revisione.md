# Quaderno della revisione

| Data | Ramo | Dove | Cosa cambiare | Stato |
|---|---|---|---|---|
| 05/10 | `fix/f1-e` | commit `fff108a` | Messaggio del commit sbagliato (contiene solo `tests/test_leveling_daily_work_insieme.py`). La storia non si riscrive: annotato | chiuso |
| 05/10 | `fix/f1-135` | `core/repositories/guild_clan_repo.py:494-505` (`remove_member`) | Ordine dei blocchi opposto a `set_member_role` (qui gilda poi membro, là membro poi gilda): deadlock se il co-owner esce mentre viene retrocesso (provato, `DeadlockDetectedError`). Bloccare prima il membro (`SELECT ... FOR UPDATE`), poi la gilda; aggiungere test | aperto |
| 05/10 | `fix/f1-135` | `cogs/leveling/leveling.py` boost (~1956, ~1996) | `buy_*_boost` danno `None` anche per non-membro/gilda assente: l'utente legge "non hai abbastanza coin". Minore | aperto |
| 05/10 | `fix/f1-133` | `cogs/utility/greetings.py:~73` | M 10.16 non consegnata: `segna_raid` non ha chi lo legge. Aggiungere `raid_in_corso` prima del DM di benvenuto + test | aperto |
| 05/10 | `fix/f1-133` | `tests/test_verify_config_cache_133.py` | Manca il test per `_invalida` dopo la scrittura (`verify_repo.py` righe ~175, ~199): tolto, i test passano | aperto |
| 05/10 | `fix/f1-133` | `cogs/security/anti_raid.py:200` | Parametro `dm_al_proprietario` di `_alert_staff` non più usato (codice morto) | aperto |
| 05/10 | `fix/f1-133` | `revisione/SPEC.md`, `VERIFICA_LIVE.md` | Non toccati: simbolo M 10.16 / §7.1 e prove live (avviso unico, ruolo con posizione e membri, tag forum) | aperto |
| 05/10 | `fix/f1-134` | `revisione/03-verifica/VERIFICA_LIVE.md` | Non toccato: aggiungere prove live di #134 (`/voice lock` con altri permessi di @everyone su un vocale temp; `/voice kick` di utente assente; log avanzati su server non sbloccato quando il modulo è premium) | aperto |
| 05/10 | `fix/f1-134` | `cogs/logging/advanced_logs.py:4-9` | Docstring in testa dice "solo se il server ha sbloccato" ma non cita `logging_avanzato_attivo`: una riga | aperto |
| 05/10 | `feat/boost-146` | `COMMAND_LIST.md:67-68` | Le due righe `/clan boost gilda` e `individuale` non citano l'opzione `tipo` (exp, coin, super) né i prezzi D23. Aggiornare | aperto |
| 06/10 | `feat/f7-quadro` | `core/premium.py:457` | `error_counter` non conta più i rifiuti `AccessoNegato`: scelta non chiesta dalla scheda e nessun test la protegge (tolta, 69 test passano). Aggiungere test (contatore non cresce su AccessoNegato, cresce sugli altri) oppure togliere la condizione | aperto |
| 06/10 | `feat/f7-quadro` | `core/command_access.py:50` | Commento "None = nessun ruolo" falso: nessuna regola ha None. Correggere | aperto |

## 06/10/2026 · #76 `feat/f7-quadro` riconsegna (9cf475e...6cfe06b)
APPROVATO. Punti precedenti chiusi (test contatore errori; commento). Import/rollback di altre chiavi invariati (il controllo guarda solo admin/mod/modban). Nota non bloccante: il rollback di una voce che rimetterebbe un ruolo ormai cancellato viene rifiutato con messaggio che nomina la chiave.

## 11/10/2026 · #76 `feat/f7-decoratore` (4903ef0...d39e1ea) REVISORE A: moderation, security, automod, logging, utility, ai
Esito DA SISTEMARE (solo rifiniture, nessuna logica cambiata di nascosto; 172 test dell'area verdi).
| 11/10 | `feat/f7-decoratore` | `cogs/utility/owner_premium.py:~290` | `cog_load` che toglie `/owner` dall'albero globale: nessun test fallisce senza (tolto, 3 test verdi) e nessun codice oggi lo aggiunge. Test che lo prova oppure togliere il blocco | aperto |
| 11/10 | `feat/f7-decoratore` | `cogs/security/anti_raid.py:~240` | `await super().cog_unload()` non protetto: tolto, 89 test verdi. Test: dopo `remove_cog` il sotto-gruppo `antiraid` non c'è più | aperto |
| 11/10 | `feat/f7-decoratore` | `cogs/utility/backup.py:17`, `ping.py:33`, `snipe.py:31` | `from discord import app_commands` ora inutilizzato (ruff F401, prima puliti) | aperto |
| 11/10 | `feat/f7-decoratore` | `tests/test_owner_blacklist_commands.py` (4 punti), `test_owner_premium_*` | `@pytest.mark.asyncio` doppio lasciato dopo aver tolto i test "rifiuta non owner" | aperto |
| 11/10 | `feat/f7-decoratore` | mappa §5 / `cogs/moderation/*` | Controlli per sotto-comando `manage_messages` (clear), `manage_channels` (lock, slowmode), `kick_members` (kick) e `view_audit_log` (log cerca/esporta) non ci sono: non c'erano neanche prima, ma la mappa li scrive. Decide l'orchestratore | domanda |

## 11/10/2026 · #76 `feat/f7-decoratore` (4903ef0...d39e1ea) REVISORE B: leveling, tickets, voice_temp, music, fun, main.py, command_sync, migrazione 0021, test di supporto
Esito DA SISTEMARE (solo rifiniture: corpi dei comandi invariati, custom_id invariati, sync e migrazione corretti).
| 11/10 | `feat/f7-decoratore` | `main.py:415` | Messaggio di benvenuto a ogni server nuovo dice "Run `/setup`": il comando non esiste più. Metti `/admin setup attiva`. Stesso per `main.py:427,434` (`/owner announce` → `/owner system announce`) e `:562` (log: `/owner eval, shell, cog-load` → `/owner system eval`, `system shell`, `cog load`) | aperto |
| 11/10 | `feat/f7-decoratore` | `tests/test_riferimenti_comandi.py:24,45` | Il test non vede i riferimenti tra apici inversi o virgolette (la forma più usata: `` `/clan lascia` ``) e non legge `main.py`: per questo il punto sopra passa. Togli `` ` ' " `` dal lookbehind, aggiungi `main.py`, aggiungi un caso con apici inversi in `test_il_riconoscitore_...` (dopo, rilancia: guarda cosa esce) | aperto |
| 11/10 | `feat/f7-decoratore` | `cogs/music/player.py:135-139` | `cog_load` che toglie `/owner` dall'albero globale: nessun cog definisce più un Group `owner`, tolto il blocco 12 test verdi. Codice morto (come `owner_premium.py:~290`): toglilo, `main.py` ha già la rete | aperto |
| 11/10 | `feat/f7-decoratore` | `tests/test_f7_gestione_livelli_gruppi.py:130` | `assert not percorsi_del_gruppo("gestione")` dipende dall'ordine: dopo `test_tickets_cog_smoke` / `test_voice_temp_cog_smoke` (che non scaricano il cog) fallisce. Controlla solo i percorsi del cog scaricato, oppure gli smoke chiamano `close_full_bot`/`remove_cog` | aperto |
| 11/10 | `feat/f7-decoratore` | `tests/test_command_sync.py:12` | `import pytest` inutilizzato (ruff F401, nuovo) | aperto |
| 11/10 | `feat/f7-decoratore` | `cogs/music/player.py:568,569,756`, `main.py:592` | Commenti con nomi vecchi (`/loop queue`, `/nonstop`, `/play`) → `/music loop queue`, `/music nonstop`, `/music play` | aperto (bassa) |
| 11/10 | `feat/f7-decoratore` | `core/command_groups.py:34` | Il testo dice che `registra_gruppi_usati` è la rete di sicurezza di `main.py`, ma `main.py` non la chiama (solo test). O la chiami o correggi il testo (fuori dai miei file) | domanda |
