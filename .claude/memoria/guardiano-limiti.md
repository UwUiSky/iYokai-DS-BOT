# Memoria di guardiano-limiti

## Aggiornata
05/10/2026 · ramo `main` · ultimo commit `3dc9031`

## In corso
- Niente a metà.

## Fatto
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

## Aperto
- Parte B del quaderno: cercare cos'altro l'API offre e discord.py no.
- Trasformare in test i limiti di `LIMITI.md` che ancora non lo sono.
- Disegni da controllare prima del codice: #138, #139, #141.
