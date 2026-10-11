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

## 11/10/2026 · #147 `feat/147-cerca-comando` (a56c96b...e669c36)
Esito DA SISTEMARE (smoke 350 verdi; logica e dati corretti; restano 6 rilievi).
| 11/10 | `feat/147-cerca-comando` | `cogs/utility/command_search.py:83` | `invalida_id` non ha nessun chiamante: la cache degli ID non si aggiorna "dopo ogni sync" (commit e DECISIONI lo promettono). Chiamarla dopo la sync (main.py/command_sync) oppure toglierla e correggere le frasi | aperto |
| 11/10 | idem | `tests/test_command_search_panel_logic.py:86` | Il test dei sinonimi passa anche senza sinonimi (la frase trova già "utente"): provato `for variante in []`. Usa una query che si lega solo per sinonimo (`"cacciare"`, `"allontana"`) | aperto |
| 11/10 | idem | `core/command_search_logic.py:90,230` | Il bonus sottostringa vale anche per le varianti: `"cacciare"` → variante `"ban"` → trova `modban lista mostra` (non c'entra). Niente bonus sottostringa per le varianti, o confronto a parola intera + test | aperto |
| 11/10 | idem | `tests/test_command_search_bug147.py:211`, `test_command_search_panel_logic.py:119,86,93` | Senza il fix passano lo stesso: `pulita[:100]` (command_search.py:227), url>512, ramo "percorso esatto", `serve` con l'ultimo comando (command_search.py:~137), pulizia in `cog_load`. Un test ciascuno | aperto |
| 11/10 | idem | `core/command_search_logic.py:96`, `:12-13` | `search_commands` senza chiamanti in produzione (solo test): codice morto/duplicato di `cerca`. Toglilo o fai usare a `cerca`. Docstring di testa con "DA FARE #77 F8" ormai vecchio; docstring del cog (1-15) non dice di pannello, `-chiedi`, `command_usage` | aperto |
| 11/10 | idem | `tests/test_command_search_bug147.py:24`, `command_search_logic.py:157,282` | ruff: `NOME_CHIEDI` inutilizzato; E741 variabile `l` | aperto (bassa) |
| 11/10 | idem | `command_search.py:142,165` | `WIKI_BASE_URL` letto con `os.getenv` e assente da `.env.example` (D16). Decide l'orchestratore: portarlo in `core/config.py` + `.env.example` | domanda |
| 11/10 | idem | #147 | Non fatti (voluti dall'autore): `scripts/genera_wiki.py` (dev-web/F10), voce in `data_registry` (F5, file ancora scheletro). La issue resta aperta: il ramo usa solo `Refs` | domanda |

## 11/10/2026 · #67 `feat/67-feed-alert` (a56c96b..f3f90f5) voci 11.1–11.10
Esito DA SISTEMARE (logica e sicurezza corrette; mancano 2 test e la documentazione). Smoke 227 verdi; mutazioni in copia: 21 su 23 fanno fallire un test.
| 11/10 | `feat/67-feed-alert` | `core/youtube_watcher.py:~135` | `if all(i in gruppi_riusciti ...)` (gruppo videos.list fallito = canale saltato, niente falso "ha terminato la diretta"): messo `if True` 74 test verdi. Test: 2 gruppi, il secondo risponde 500, il canale con ID nel secondo non cambia stato | aperto |
| 11/10 | `feat/67-feed-alert` | `core/feed_watcher.py:~96` | `self._etag_per_url.pop(url, None)`: tolto, 74 verdi. Il test "etag non ricordato" parte senza ETag, quindi non lo prova. Test: tick 1 riuscito (ETag salvato), il feed cambia, tick 2 con `update_last_seen` che solleva, tick 3 deve essere 200 | aperto |
| 11/10 | `feat/67-feed-alert` | `core/youtube_api_logic.py:41`, `tests/test_youtube_api_logic.py` | `parse_search_live_response` senza chiamanti (la memoria di dev-utilita lo dice): codice morto. Togli funzione, import e suoi test; riscrivi docstring righe 1-30 ("Perché search.list") | aperto |
| 11/10 | `feat/67-feed-alert` | `core/config.py:205-208`, `revisione/SPEC.md:883,2235` | Dicono ancora che il live usa `search.list` a 100 unità: ora è RSS + `videos.list`. Aggiorna anche lo stato di 10.4 | aperto |
| 11/10 | `feat/67-feed-alert` | `revisione/03-verifica/VERIFICA_LIVE.md` (~380-396) | Nessuna voce per ciò che solo Discord/YouTube/Twitch veri provano: YouTube live con RSS + `videos.list`, 304 reale con ETag, Twitch oltre 20 stream, 26º feed rifiutato, modulo spento. Aggiungi | aperto |
| 11/10 | `feat/67-feed-alert` | `core/feed_alert_gate.py:14` | `MODULE_FEED_ALERTS` duplicata in `cogs/utility/feed_alerts.py:31`: importa dal gate (una sola costante) | aperto (bassa) |
| 11/10 | `feat/67-feed-alert` | `core/youtube_watcher.py:189` | Manca la riga vuota prima di `async def close` | aperto (bassa) |
| 11/10 | `feat/67-feed-alert` | `core/twitch_watcher.py:~178`, `youtube_watcher.py:~150` | Canale non raggiungibile: ora lo stato non avanza, quindi il warning esce a ogni giro (prima una volta). Accettabile; decidere se loggare una volta sola | domanda |
