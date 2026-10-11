# Memoria di dev-utilita

## Aggiornata
11/10/2026 · ramo `feat/67-feed-alert` · #67 voci 11.1-11.10 (salto 11.11, 11.12)

## In corso
- Previsione: chiudere 11.1-11.10 in 4 commit (Twitch, YouTube, feed, rete).
  Fatti: Twitch (11.2, 11.3, 11.4 e 11.6 Twitch). 11.7 e 11.10 erano gia' a posto
  (test esistenti). Prossimo: YouTube (11.1 RSS + videos.list, 11.4, 11.6), poi
  feed (11.4, 11.5, 11.8), poi rete (11.9).
- Gate modulo: `core/feed_alert_gate.filtra_attive`; i test patchano
  `core.feed_alert_gate.modulo_alert_attivo`.

## Fatto
- #67 Twitch: first=100, blocchi da 100 senza doppioni, 401 svuota token, modulo spento, render_template.
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
