# Memoria di guardiano-limiti

## Aggiornata
11/10/2026 · controllo del diff su `feat/f7-decoratore` (copia `/home/claude/wt/f7d`, commit `4fe0765`)

## In corso
- Niente a metà.

## Fatto
- 11/10: albero reale F7 dopo D24 misurato (script `albero2.py` nello scratchpad): REGGE. 16 globali + `/owner` (5 figli) nel server; 252 foglie contro 253 vecchie (fusione voluta `logs-setup`+`mod-log-setup`); max 4816 caratteri (`/gestione`); `/admin` 2738. Nessun limite superato.
- 05/10: disegno albero F7 (D24) misurato sull'albero vero: `/admin` a 22 figli = 9241 caratteri (>8000). Esito: 16 gruppi. Tabella in `revisione/02-piano/MAPPA_COMANDI_F7.md`.
- `revisione/01-analisi/LIMITI.md`: 57 limiti (LIM-1…57) e lista di
  controllo (Parte 4), scritti il 04/10.
- Verificato sul codice installato: discord.py 2.7.1 legge i messaggi
  vocali ma non li invia (#142).

## Cose imparate
- `/setup` era rotto per 35 voci in un menu da 25: ogni elenco che
  cresce con i moduli va diviso o paginato **dal disegno**.
- Comandi di primo livello: 97 su 100. `/owner`: 25 su 25.
- Dal luglio 2025 un bot non crea server (`create_guild` deprecato).
- Dal 23/02/2026 permessi divisi: `PIN_MESSAGES`, `BYPASS_SLOWMODE`,
  `CREATE_GUILD_EXPRESSIONS`, `CREATE_EVENTS`.
- Voce cifrata (DAVE) obbligatoria dal 01/03/2026: Lavalink 4.2.0+.
- Intent privilegiati: soglia a 10.000 utenti, domanda da rifare ogni
  anno. Verifica dell'app: 100 server.
- Un nodo wavelink vale per **un solo** bot (LIM-40).
- Invio file: Discord dà 20 MiB di partenza, discord.py ne assume 10.
- Offuscamento dei canali obbligatorio dal 16/11/2026: da seguire.
- Le chiamate dirette all'API passano da `bot.http.request(Route(...))`;
  `/restore-users` usa ancora `aiohttp` a mano.

- Gli 8000 caratteri contano tutti i figli, anche nei sotto-gruppi: i sotto-gruppi risolvono i 25 figli, non gli 8000. Misura: `tree.get_commands()` + `to_dict(tree)`.
- Oggi nessun comando ha `default_permissions` né `guild_only`; `/owner` è globale.
- `/config language set` è già a 3 livelli: sotto un gruppo va appiattito.

## Aperto
- Sync senza impronta (`main.py:304-319`): proporre l'hash dell'albero all'orchestratore (quaderno, Parte A).
- `-cerca-comando` non è nella tabella §5 (permessi/guild_only): oggi senza permessi e usabile in DM; chiedere all'owner.
- Descrizione di `moduli alert feed:feed_url` lunga esattamente 100: nessun margine.
- Il test dei caratteri esiste già (`test_command_tree_invariants.py`).
- Owner deve approvare 13 -> 16 gruppi (D24).
- Parte B del quaderno: cercare cos'altro l'API offre e discord.py no.
- Trasformare in test i limiti di `LIMITI.md` che ancora non lo sono.
- Disegni da controllare prima del codice: #138, #139, #141, #142
  (voce: confermare sulla pagina ufficiale le regole dei vocali).
