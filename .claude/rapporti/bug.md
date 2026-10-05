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
