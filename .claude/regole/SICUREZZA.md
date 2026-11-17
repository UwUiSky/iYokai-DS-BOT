# Regole di sicurezza (vincolanti)

Valgono per ogni riga di codice, di chiunque: persona, Sonnet, Opus o altro.
Chi scrive le applica; chi rivede le controlla una per una sul diff.
Una voce non rispettata blocca l'unione in `main`.

## 1. Tutto ciò che arriva da fuori è ostile

"Da fuori" = testo, nomi, file, link, ID, JSON di utenti, di altri bot, di
servizi esterni e del pannello web.

- **Permessi prima di tutto.** Ogni comando, bottone, menu, finestra e rotta web
  controlla chi chiama **in quel momento** e **su quel server**. Mai fidarsi di
  un ID scritto in un `custom_id`, in un campo nascosto o in un JSON.
- **Gerarchia dei ruoli.** Prima di agire su un membro o un ruolo: il bersaglio
  sta sotto chi comanda **e** sotto il bot. Mai agire sul proprietario del server.
- **Menzioni.** Ogni messaggio con testo di un utente parte con
  `allowed_mentions` esplicito (di norma tutto spento).
- **Testo mostrato.** Nomi e testi di utenti passano dalla pulizia prima di
  finire in embed, log, nomi di canali o di webhook: niente accenti gravi che
  escono dal blocco, niente link mascherati `[x](url)`, niente caratteri di
  controllo o invisibili. Lunghezze sempre tagliate ai limiti di Discord.
- **Espressioni regolari scritte da utenti:** solo con `re2` (mai `re`), con
  tetto di lunghezza.
- **Modelli e script degli utenti** (tag, comandi personalizzati): solo
  l'interprete chiuso che c'è già. Mai `eval`, `exec`, `format` con oggetti veri,
  `getattr` su nomi scelti dall'utente.

## 2. File e allegati (D61, D62, D74)

- Il processo del bot **non apre mai** un file di un utente. Lo apre solo la
  sandbox (`core/immagini_sandbox.py`, `core/conversioni_worker.py`).
- Il tipo si decide **dai primi byte** (`core/allegati_tipo_logic.decidi`), mai
  dal nome o dal content-type.
- L'originale **non si conserva e non si rimanda**. Esce solo la copia rifatta
  (`core/allegati_copia.copia_sicura`) oppure la scheda (nome pulito, tipo, peso).
- Mai mostrare il link di Discord all'allegato originale di un utente.
- Un nome di file non diventa mai un percorso su disco. Sul disco solo nomi casuali.
- Ogni lavoro pesante ha tetti di byte, pixel, pagine, durata, tempo e memoria.
  Ucciso o scaduto = nessuna copia.

## 3. Rete

- Un URL scelto da un utente si scarica **solo** con `core/safe_http`
  (niente reti private, redirect limitati, tetto di byte e di tempo).
- Mai passare a Lavalink, ffmpeg o a un altro programma un URL o un percorso
  non controllato. ffmpeg: lista di argomenti, formato in entrata esplicito,
  `-protocol_whitelist file,pipe`, mai una shell.
- Server HTTP del bot: in ascolto su `127.0.0.1`, dietro un proxy. `X-Forwarded-For`
  vale solo dai proxy fidati.

## 4. Database

- Valori **sempre** come parametri (`$1`, `$2`). In una stringa SQL entrano solo
  nomi di colonna presi da un elenco fisso nel codice, controllati con
  `raise ValueError` (mai con `assert`).
- Ogni tabella con dati personali entra in `core/data_registry.py` (cancellazione,
  copia dei dati, scadenza).
- Operazioni che devono valere una volta sola: transazione, `FOR UPDATE` o
  vincolo unico. Mai "leggo, poi scrivo" senza blocco.

## 5. Segreti

- Nessun segreto in repository, commit, issue, log, messaggi d'errore, URL, chat.
- A riposo: cifrato (`core/oauth_crypto`) se va riletto, solo impronta SHA-256
  se va confrontato. Confronti con `hmac.compare_digest`.
- Nei log l'URL va senza query; i campi segreti di `Config` hanno `repr=False`.
- Il modello `.env.example` parte in `production`, con `eval` e hot patch spenti.

## 6. Pannello web e interfacce HTTP

- Sessione: cookie `__Host-`, HttpOnly, Secure, SameSite=Lax; nel database solo
  l'impronta.
- Ogni scrittura: token CSRF **e** controllo dell'`Origin`.
- Pagine: Jinja con escape automatico, CSP senza script (tranne le eccezioni già
  scritte), mai HTML costruito a mano con dati di utenti.
- Limite di richieste per IP (anonimi) e per utente (loggati), limite sul corpo.
- Un errore non mostra mai dettagli interni.

## 7. Abuso e costi

- Ogni comando che costa (rete, sandbox, AI, database pesante) ha una pausa per
  utente e un tetto per server. `defer()` prima del lavoro lento.
- Liste con tetto o a pagine. Cache e code sempre con un massimo.
- Ciò che un utente può far partire tante volte (reazioni, link, messaggi) non
  deve poter riempire la coda della sandbox né le quote dei servizi esterni.

## 8. Comandi pericolosi

- `/owner eval`, `/owner shell`, caricamento dei cog e hot patch: spenti in
  produzione. Non aggiungerne altri. Niente che esegua codice arrivato da Discord.
- Processi esterni: sempre lista di argomenti, timeout, ambiente ridotto.

## 9. Come si rivede (chi fa l'ultimo controllo)

Per ogni file toccato dal diff, rispondere per iscritto:

1. Da dove entra un dato non fidato? Dove viene controllato?
2. Chi può chiamare questo codice? Il permesso è controllato qui o si dà per scontato?
3. Cosa succede con input vuoto, enorme, ripetuto mille volte, in contemporanea?
4. Cosa succede se il servizio esterno, la sandbox o il database non rispondono?
   (Nel dubbio si deve chiudere: nessun file, nessuna azione.)
5. Qualcosa finisce in un log, in un messaggio o in un file che non dovrebbe?
6. C'è un test che fallisce senza la protezione?

Un difetto trovato si dimostra con un test che fallisce, poi si corregge.
