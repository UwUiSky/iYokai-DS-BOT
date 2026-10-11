# Memoria di dev-utilita

## Aggiornata
11/10/2026 · ramo `feat/67-feed-alert` · #67 voci 11.1-11.10 (salto 11.11, 11.12)

## In corso
- #67 chiusa tranne 11.11 (F5) e 11.12 (F13), non miei in questo giro. Niente a meta'.
  11.7 e 11.10 erano gia' a posto (test esistenti). Da fare: rapporto, smoke, push del ramo.

## Fatto
- #67 revisione: test gruppo 500 YouTube e ETag a 3 giri, tolto parse_search_live_response, config/SPEC aggiornati, VERIFICA_LIVE, avviso canale una sola volta (AvvisoUnaVolta).
- #67 correzioni cacciatore-bug: videos.list senza maxResults, tetto 25 atomico (lock advisory), avanzamento dopo invio, ETag dopo elaborazione completa, data GREATEST, sessione chiusa al cambio loop, elenco con righe troncate.
- #67 Rete: safe_get con sessione condivisa, User-Agent, ETag; feed_watcher scarica gli URL uguali una volta (in parallelo, max 5).
- #67 Feed: modulo spento, data ultimo pubblicato (migrazione 0023, id sparito = niente doppioni), tetto 25 feed e elenco tagliato.
- #67 YouTube D5: RSS per canale (safe_get) + una videos.list per 50 ID; modulo spento = zero quota.
- #67 Twitch: first=100, blocchi da 100 senza doppioni, 401 svuota token, modulo spento, render_template.
- F7 2c: /owner (premium, blacklist, cog, system) ad5ad8e; /admin + /moduli ce9f6b9;
  /utility 38bd97e; -cerca-comando 472c185. Refs #76.
- Voci rapide F1: limiti di `/poll`, `/search`, messaggi fissi, ID di `/alerts`.

## Cose imparate
- Lo stato (last_seen, last_known_live) avanza solo dopo `send` riuscito; ETag solo se nulla da ritentare.
- videos.list: `id` e `maxResults` insieme danno 400.
- Sessione condivisa di safe_http legata al loop: i test che la usano chiamano `chiudi_sessione_condivisa()`.
- Watcher avvisi: i test patchano `core.feed_alert_gate.modulo_alert_attivo`; ETag mai se una sottoscrizione ha last_seen vuoto.
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
