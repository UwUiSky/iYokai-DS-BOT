# Memoria di dev-utilita

## Aggiornata
11/10/2026 · ramo `feat/147-cerca-comando` (base a56c96b) · #147 chiusa tranne wiki/AI/sinonimi estesi

## In corso
- Niente a metà. Giro #147: previste 1 voce (pannello+ricerca+usage+-chiedi+wiki bottone), chiusa.
- Prossimo (orchestratore): unire il ramo; poi `/gestione` (greetings, role_menus),
  `nonstop-main` -> `/owner radio`, `/report` e `/report-setup`,
  `registra_comandi_del_cog` deve saltare `owner` (core/command_groups.py).

## Fatto
- #147: pannello `-cerca-comando`, ricerca+completamento, `command_usage` (0022), `-chiedi`,
  bottone wiki (WIKI_BASE_URL), sinonimi. Ramo feat/147-cerca-comando.
- F7 2c: /owner ad5ad8e; /admin + /moduli ce9f6b9; /utility 38bd97e; -cerca-comando 472c185. Refs #76.
- Voci rapide F1: limiti di `/poll`, `/search`, messaggi fissi, ID di `/alerts`.

## Cose imparate
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
- F1 resto: #66, #67 (utilità e avvisi).
- #147 non fatto: `scripts/genera_wiki.py` (dev-web), AI (F12). WIKI_BASE_URL letto con os.getenv:
  da portare in core/config.py (non nostro) + .env.example.
- Registro dati personali (F5, core/data_registry.py + forget_user_service): aggiungere `command_usage`
  (chiave user_id e guild_id, 90 giorni, tetto 200.000 righe).
- Menzioni di `/owner` non mostrate nel pannello (è solo nel server owner).
