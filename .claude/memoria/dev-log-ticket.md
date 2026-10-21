# Memoria di dev-log-ticket

## Aggiornata
21/10/2026 · ramo `feat/r8tkt` (copia /home/claude/wt/r8tkt, DB iyokai_wr8tkt) · base fa3f4a5 · migrazioni 0220–0229

## In corso
- Giro r8 chiuso (5 gruppi su 5). Ramo pronto per cacciatore-bug/revisore. Nessun passo aperto.
- #142 (voce di Yokai) non iniziato: serve il guardiano-limiti, un motore TTS e la voce scelta dall'owner.

## Fatto
- Giri F1–r4: router NF-01/02, snipe NF-03, M 5.x, M 6.1-6.9, #145, NF-13, NF-33, #139 senza AI, #119, #127; su main.
- r8: 3680adb base 0220 + apertura · 3ade231 /ticket opzioni, lista-nera, sospendi, azzera-pausa, reperibile, apri ·
  4d220ad presa/chiusura/note/chiedi-chiusura · 98a1d4c #139 AI · 6d3d6b2 documenti. /ticket 21 figli. Migrazione 0220 sola.

## Cose imparate
- Rinomine sempre da `core/channel_rename.py`; cancellazione dei ticket dallo scheduler, non da un task.
- `channel.set_permissions(x, connect=False)` SOSTITUISCE l'overwrite di x: `overwrites_for` + `update` + `overwrite=`.
- Listener premium: `core.security_access.premium_sbloccato(guild_id, modulo, bot)`; nei test bot finto con `get_guild` -> None.
- Nei test dei vocali `Scena` (tests/test_voice_temp_correzioni.py); `overwrites_for.return_value` dal test.
- `can_moderate` nega i ruoli pari: proprietario e bot con `top_role` (helper `_con_ruolo`).
- F7: `@comando_di_gruppo` + `CogConGruppi`; i test con `bot.add_cog` fanno `remove_cog` (GRUPPI globali).
- Router: destinazione = riga `output_channels`, altrimenti `log_channel_id`; test senza DB con `router_fakes`.
- Proprietario: `guild.get_member(guild.owner_id)`, non `guild.owner`.
- Un nome `test*` importato in un file di test viene raccolto: importare il modulo.
- Ogni log passa da un interruttore (core/log_eventi_logic.py, INTERRUTTORI); D15: chi scrive lo decide core/bot_roles.py.
- DynamicItem: `interaction_check` con `super()` + blacklist (test_ui_base_wiring).
- Metodo di repository nuovo = chiamante in produzione; tabella nuova = core/data_registry.py (figlie prima).
- Niente chiavi nuove in guild_config.settings: tabella propria.
- Misura dei gruppi: scratchpad/tkt_peso.py (stdout solo, 2>/dev/null). Traduzioni: aggiungere senza riordinare il JSON.
- Migrazione cambiata dopo l'applicazione: DROP tabelle + `DELETE FROM schema_migrations WHERE version=N`.

## Aperto
- Router: sanzioni, automod, allarmi e benvenuto non passano ancora dal router (§18.1 `[~]`).
- #144: /voice lock dopo un riavvio perde un connect=True originale (serve colonna: decide l'orchestratore).
- Smoke r8: fallisce test_config_import_validation per `backup_livello_permessi` (core/backup_permessi_logic.py, area
  backup, già su main fa3f4a5): non mio.
- #120 restano TKT-006, 026, 027, 029, 031, 032, 035, 045, 046, 051, 063, 064, 067, 068, 070, 071, 073, 074, 079, 088.
