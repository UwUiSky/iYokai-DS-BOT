# Memoria di dev-utilita

## Aggiornata
11/10/2026 · ramo `feat/f7-admin-utility` (base 0fd15a7) · F7 passo 2c chiuso

## In corso
- Niente a metà. Prossimo (orchestratore): `/gestione` (greetings, role_menus),
  `nonstop-main` -> `/owner radio` (sta in cogs/music/player.py), `/report` e
  `/report-setup` (sono in cogs/moderation/report.py), `registra_comandi_del_cog`
  deve saltare `owner` (core/command_groups.py).

## Fatto
- F7 2c: /owner (premium, blacklist, cog, system) ad5ad8e; /admin + /moduli ce9f6b9;
  /utility 38bd97e; -cerca-comando 472c185. Refs #76.
- Voci rapide F1: limiti di `/poll`, `/search`, messaggi fissi, ID di `/alerts`.

## Cose imparate
- `@comando_di_gruppo` va sopra describe/choices; il permesso lo dà il gruppo.
- `registra_comandi_del_cog` mette anche `owner` nell'albero globale: i cog owner
  fanno `tree.remove_command("owner")` in cog_load; main.py lo toglie e usa
  `registra_owner` solo per MAIN_GUILD_ID.
- I test dei percorsi usano `tests/support/percorsi.py` (GRUPPI è globale al processo).
- test_command_policy: `automod` senza permessi e 5 gruppi non guild_only falliscono
  già in base (non nostri).
- `/admin lingua show|set`: lingua è un sottogruppo di /admin (non sotto config).

## Aperto
- F1 resto: #66, #67 (utilità e avvisi).
- Prova live: vedi rapporto F7 2c.
