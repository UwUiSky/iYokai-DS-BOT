# Quaderno dei bug

| Data | Dove | Cosa | Gravità | Stato |
|---|---|---|---|---|
| 05/10 | `cogs/moderation/actions.py`, `softban_mute.py` | Messaggio privato di kick e ban mandato dopo l'azione: non arriva | alta | issue #137 |
| 05/10 | `cogs/security/anti_nuke.py` | Cancellazioni sotto soglia mai recuperate; ruoli senza posizione né membri; tag dei forum persi | media | issue #133 |
| 05/10 | `cogs/security/anti_raid.py` | Un avviso per ogni ingresso; ruolo "Quarantined" esistente non aggiornato | media | issue #133 |
| 05/10 | `cogs/automod/automod.py` | Liste dei link senza tetto | bassa | issue #133 |
| 05/10 | `cogs/voice_temp/voice_temp.py` | `/voice kick` dice "espulso" se l'utente non è nel canale; `/voice lock` riscrive tutti i permessi di @everyone | media | issue #134 |
| 05/10 | `cogs/tickets/tickets.py` | Usa `db._remove_guild_setting` (funzione privata) | bassa | issue #134 |
| 05/10 | `cogs/leveling/leveling.py` (clan) | `/clan boost` paga due volte con due clic; `/clan tesoreria dona` in due transazioni; `/clan promuovi` supera il tetto | alta | issue #135 |
| 05/10 | `tests/conftest.py` | `reset_premium_registry` non ripristina `is_premium_active` | bassa | issue #135 |
| 05/10 | `cogs/utility/config_history.py` | `/config export` scrive `null` che l'importazione rifiuta | media | issue #136 |
| 05/10 | `tests/test_backup_orchestrator.py` | Un test dipende dall'ordine di esecuzione | bassa | annotato in #68 |
| 05/10 | `guild_clan_repo.py:521` (`set_member_role`, ramo fix/f1-135) | Blocca prima `clans` poi la riga membro; `apply_text_tick` (:835) fa il contrario: deadlock se un messaggio e una promozione arrivano insieme (prova: 150 giri, errore 4 volte su 4; sul 5c04cf5 0 su 4). Rimedio: bloccare prima la riga membro, poi `clans` | media | confermato, da correggere nel ramo |
| 05/10 | `guild_clan_repo.py` (`buy_member_boost`, `donate_from_member`, `set_member_role`) | Il repository non controlla che clan e `guild_id`/utente combacino (coin di un altro server spese; non-membro promosso co-owner). Il cog protegge | bassa | plausibile |
| 05/10 | `config_history.py:446` | L'export toglie i `null` di primo livello ma non quelli dentro le liste, né le chiavi fuori schema: l'import li rifiuta | bassa | plausibile |
| 05/10 | `leveling.py` boost | Due pagamenti sommano 48h (voluto dal test, domanda all'owner) | - | domanda |
| 05/10 | `core/repositories/verify_repo.py:96` (fix/f1-133) | Cache config verifica: lettura lenta in corso + `set_config` in mezzo, poi la lettura rimette il valore vecchio in cache (resta vecchio fino al prossimo scrittore/riavvio) | media | confermato, prova `scratchpad/cb133/prova.py` |
| 05/10 | `cogs/security/anti_raid.py:_avvisa` (fix/f1-133) | Nessun blocco: N ingressi insieme vedono `messaggio None` e mandano N messaggi (provati 5 su 5) | media | confermato |
| 05/10 | `cogs/security/anti_nuke.py:_evento` (fix/f1-133) | `_in_attesa` senza scadenza: cancellazioni legittime vecchie vengono ricreate quando l'autore supera la soglia ore dopo | media | confermato (lettura) |
| 05/10 | `core/security_raid_state.py` (fix/f1-133) | `raid_in_corso()` non ha chiamanti: benvenuto/verifica non tacciono durante il raid | bassa | confermato (grep) |
| 05/10 | `core/premium.py:300-317` via `advanced_logs.py:181` (fix/f1-134) | Con il modulo premium e il server non sbloccato (o sbloccato solo da abbonamento) ogni evento fa 3 query senza cache (whitelist, cassa, abbonamento): 5 eventi = 15 query. `on_voice_state_update` scatta a ogni ingresso/uscita; i server negati con modulo acceso le pagano comunque. Come gli altri moduli premium, ma qui la frequenza è alta | media | confermato, `scratchpad/cb134/conta.py` (PREMIUM_ALPHA_UNLOCK_ALL=false) |
| 05/10 | `voice_temp.py:kick` (fix/f1-134) | Nessun controllo di gerarchia: il proprietario non-staff può espellere un admin/staff dal proprio canale (il bot ha Move Members). Non cambiato dal diff | bassa | plausibile |
| 05/10 | `voice_temp.py:lock/unlock` (fix/f1-134) | Sblocco rimette `connect=None`, non il valore di prima: un `connect=True` messo da altri su @everyone si perde. Oggi i canali nascono senza override, quindi non succede | bassa | plausibile |
| 05/10 | `tests` fix/f1-134 | Con più pytest insieme sul DB `iyokai_wt134` (`clean_db` svuota le tabelle) i test voice/premium falliscono a caso: 44/44 verdi due volte a DB libero. Non è un bug del ramo | - | nota |
