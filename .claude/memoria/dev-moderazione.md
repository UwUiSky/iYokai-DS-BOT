# Memoria di dev-moderazione

## Aggiornata
05/10/2026 · ramo `fix/f1-133` (base `5c04cf5`) · #133 chiusa nel ramo

## In corso
- Niente a metà. Prossimo giro: #137 (DM prima di kick/ban) se non già
  fatto dall'orchestratore; poi #138.

## Fatto
- F1, sicurezza + AutoMod + verifica: unito su main con `7722b71`
  (nuovo `core/security_access.py`, tabella `anti_raid_lockdown`).
- Voci rapide F1 (anti-nuke non conta il bot, anti-raid ignora i bot).
- #133 anti-nuke (`80f1894`): cancellazioni sotto soglia recuperate al
  superamento; ruolo con posizione e membri; tag dei forum.
- #133 anti-raid + M 10.16 (`fbef3b0`): un avviso aggiornato; Quarantined
  esistente adottato e allineato; `core/security_raid_state.py`.
- #133 AutoMod (`f48e6e3`): tetto 100 domini per lista link.
- #133 verifica: cache config con tetto (commit di chiusura).

## Cose imparate
- Le tabelle di sicurezza stanno in `security_repo.run_migrations`.
- Il messaggio privato di kick/ban deve partire PRIMA dell'azione.
- DATABASE_URL va esportato in OGNI chiamata di shell: senza, i test
  usano il database condiviso e si pestano con gli altri agenti.
- discord.py 2.7: dopo on_guild_role_delete `role.members` funziona
  ancora (i membri tengono l'id); `Role.edit(position=)` per la posizione.
- Il ruolo ricreato non può stare sopra il ruolo più alto del bot.
- I test di anti-raid/anti-nuke importano fixture da `test_anti_*_f1.py`.
- Un test che scrive 100 domini uno a uno costa ~25 s: tenerne pochi.

## Aperto
- M 10.16: manca l'aggancio in `cogs/utility/greetings.py` (file di
  `dev-utility`): `if raid_in_corso(member.guild.id): return` prima del
  DM di benvenuto (riga ~73), con `from core.security_raid_state import
  raid_in_corso`. La verifica (`cogs/security/verify.py`) non invia DM.
- #137, #138 (vedi sopra).
