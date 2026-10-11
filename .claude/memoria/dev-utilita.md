# Memoria di dev-utilita

## Aggiornata
11/10/2026 · #147 e #67 uniti in main · giro chiuso

## In corso
- Niente a metà. #147 chiusa tranne wiki script/AI; #67 chiusa tranne 11.11 (F5) e 11.12 (F13).
- Prossimo: #66 (utilità), poi `/gestione` (greetings, role_menus), `nonstop-main` -> `/owner radio`,
  `/report` e `/report-setup`; `registra_comandi_del_cog` deve saltare `owner` (core/command_groups.py).

## Fatto
- #147: pannello `-cerca-comando`, ricerca+completamento, `command_usage` (0022), `-chiedi`, bottone wiki, sinonimi.
- #67: Twitch (first=100, blocchi, 401), YouTube D5 (RSS + videos.list), feed (data ultimo pubblicato 0023,
  tetto 25 atomico), rete (sessione condivisa, ETag), modulo spento, avanzamento dopo invio, avviso una volta.
- F7 2c: /owner ad5ad8e; /admin + /moduli ce9f6b9; /utility 38bd97e; -cerca-comando 472c185. Refs #76.
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
- test_command_policy: ogni comando di primo livello nuovo va in AUDIENCE (tests/support/command_policy.py).
- `core/cog_manager` carica ogni .py di cogs/ come cog: un file di sole classi UI si chiama `_nome.py`.
- `test_repository_callers`: ogni metodo di repo deve avere un chiamante di produzione (niente metodi "per dopo").
- Ultimo comando usato: evento `app_command_completion` (discord.py 2.7) nel cog, niente toccare blacklist_tree.
- ID per le menzioni: `tree.fetch_commands()`; in sviluppo/server owner i comandi sono del server (id diversi): cache a parte.
  La cache si ricarica per TTL (1 h) o quando manca un ID (max 1/min); niente invalidazione esplicita.
- Pannello: 20 bottoni categoria (righe 0-3) + frecce e wiki (riga 4) = 23 componenti.
- Comandi con parametro opzionale: `Range[str,1,100] | None = None`.
- Il pannello filtra per livelli di gruppi e `@richiedi` (`richiedi` ora mette `predicate.livello`); fetch ID fuori dal lock, timeout 2 s; defer prima delle chiamate lente; usare `interaction.guild_id`.
- `COMMAND_LIST.md` va rigenerato (scripts/generate_command_list.py) quando cambia l'albero.

## Aperto
- F1 resto: #66 (utilità).
- #147 non fatto: `scripts/genera_wiki.py` (dev-web), AI (F12). WIKI_BASE_URL ora in core/config.py e .env.example.
- Registro dati personali (F5, core/data_registry.py + forget_user_service): aggiungere `command_usage`
  (chiave user_id e guild_id, 90 giorni, tetto 200.000 righe).
- Menzioni di `/owner` non mostrate nel pannello (è solo nel server owner).
