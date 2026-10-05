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
