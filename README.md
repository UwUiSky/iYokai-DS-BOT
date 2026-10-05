<div align="center">

# 😻 iYokai

**Bot Discord tutto-in-uno per le community: moderazione, sicurezza, musica, livelli, clan, ticket e molto altro.**

Python 3.11 · discord.py 2.7 · PostgreSQL · Lavalink

*Repository privata — in sviluppo, non ancora in produzione*

</div>

---

## Indice

- [Cos'è](#cosè)
- [Stato del progetto](#stato-del-progetto)
- [Funzioni](#funzioni)
- [Le applicazioni del progetto](#le-applicazioni-del-progetto)
- [Installazione](#installazione)
- [Configurazione](#configurazione)
- [Test](#test)
- [Struttura della repository](#struttura-della-repository)
- [Come si lavora](#come-si-lavora)
- [Documentazione](#documentazione)
- [Sicurezza e privacy](#sicurezza-e-privacy)

---

## Cos'è

iYokai è un bot **multi-tenant**: un solo programma serve molti server,
e ogni server accende e configura solo i moduli che gli servono. Tutto
si configura con i comandi slash; un pannello web è in programma e
offrirà le stesse impostazioni in forma più semplice.

Punti che lo distinguono:

- **Flotta musicale**: cinque bot musicali gestiti dallo stesso
  programma; il primo libero risponde. In più una radio 24/7 con i
  brani dell'owner.
- **Sicurezza a più livelli**: anti-raid, anti-nuke, canale trappola
  per lo spam con appello, rete di ban condivisa tra server, verifica
  all'ingresso.
- **Backup e ritorno dei membri**: copia del server su un server di
  riserva tenuto aggiornato, e rientro dei membri che hanno dato il
  consenso.
- **Economia a clan**: livelli, monete, negozio, clan con cassa,
  canali propri e classifiche.
- **Italiano per primo**, inglese in arrivo.

---

## Stato del progetto

| | |
|---|---|
| Fase attuale | **Correzione** (fase F1 di 13). Lo sviluppo di funzioni nuove riprende a correzione finita |
| Server in cui è presente | 0: non è ancora stato provato su Discord vero |
| Test automatici | 2676, tutti verdi |
| Voci della specifica | 97 fatte · 145 parziali · 246 da fare · 6 scartate ([`revisione/SPEC.md`](revisione/SPEC.md)) |
| Lavoro da fare | [Issue](https://github.com/UwUiSky/iYokai-DS-BOT/issues), una [milestone](https://github.com/UwUiSky/iYokai-DS-BOT/milestones) per fase |

Le fasi, in ordine: **F1** bug e limiti · **F2** musica · **F3** backup
e bot separati · **F5** dati e GDPR · **F6** canali di log · **F7**
struttura dei comandi · **F8** lingue · **F9** funzioni nuove · **F10**
pannello web · **F11** NSFW · **F12** AI · **F13** app utente e desktop
· **F14** idee rimandate.

---

## Funzioni

Lo stato preciso di ogni voce è in [`revisione/SPEC.md`](revisione/SPEC.md). L'elenco dei
comandi è in [`COMMAND_LIST.md`](COMMAND_LIST.md).

| Area | Cosa comprende |
|---|---|
| **Moderazione** | warn, kick, ban, ban a tempo, softban, timeout, mute, blocco canali, slowmode, pulizia messaggi, casi numerati, note, segnalazioni |
| **AutoMod** | parole vietate e inviti (AutoMod nativo), link, maiuscole, emoji, menzioni, spam, scala di sanzioni |
| **Sicurezza** | anti-raid, anti-nuke con recupero, canale trappola con appello, ban globale tra server, mappa dei permessi, punteggio di sicurezza |
| **Verifica** | bottone, reazione, ruolo verificato, liste bianche e nere |
| **Log** | ingressi e uscite, ruoli, canali, voce, server, soundboard; ricerca ed esportazione dello storico |
| **Ticket** | pannelli, categorie, presa in carico, priorità, trascrizioni, statistiche |
| **Vocali temporanei** | canale "crea il tuo", pannello di controllo, ruoli piattaforma |
| **Musica** | riproduzione con cinque bot musicali, coda, loop, 24/7, radio dell'owner |
| **Livelli ed economia** | XP testo e voce, premi di livello, monete, lavoro e premio giornaliero, negozio, giveaway, drop |
| **Clan** | creazione, cassa, canali del clan, classifiche, vincitori del mese |
| **Utility** | sondaggi, promemoria, messaggi programmati, sticky, role menu, benvenuti, suggerimenti, statistiche del server |
| **Alert** | Twitch, YouTube, feed RSS, webhook personalizzati |
| **Backup** | copia della struttura, mirror dei messaggi, snapshot dei membri, ritorno dei membri con consenso |
| **Divertimento** | filtri immagine, meme, animali, ricerca immagini, giochi |
| **Owner** | premium, blacklist, gestione dei moduli, statistiche, annunci |

In programma: canali di log per tipo e su forum, log dei messaggi,
nuova struttura dei comandi (`/owner`, `/admin`, `/mod`, `/security`…),
italiano e inglese, ruolo automatico, starboard, comandi personalizzati,
immagini di benvenuto e di livello, pannello web, app installabile
dall'utente, programma per PC, motore AI.

---

## Le applicazioni del progetto

iYokai non è un solo bot: sono più applicazioni Discord che lavorano
insieme, ciascuna con il suo token. Dividere i compiti riduce i limiti
di frequenza di Discord e isola i problemi.

| Applicazione | Compito | Stato |
|---|---|---|
| **iYokai** | Comandi, interfaccia, configurazione | in correzione |
| **iYokai Mod** | Log, AutoMod e azioni di sicurezza, separati dal principale | da fare (F3) |
| **iYokai Creator** | Porta e tiene aggiornato il server di backup | da rifare (F3) |
| **iYokai Music** ×5 | Riproduzione musicale, un canale vocale ciascuno | da correggere (F2) |
| **iYokai NSFW** | Contenuti per adulti, isolati dal resto | da fare (F11) |
| **iYokai App** | Comandi installati sull'utente, usabili in ogni server | da fare (F13) |
| **iYokai Panel** | Pannello web | da fare (F10) |
| **iYokai Desktop** | Programma per PC: stato personalizzato, notifiche, storico delle menzioni | da fare (F13) |

---

## Installazione

Serve: Python 3.11, PostgreSQL 14 o successivo, e per la musica un
server Lavalink 4.2.0 o successivo.

```bash
git clone https://github.com/UwUiSky/iYokai-DS-BOT.git
cd iYokai-DS-BOT

python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate

pip install -r requirements.lock  # versioni esatte

cp .env.example .env              # poi compila i valori
python main.py
```

Se manca una variabile obbligatoria il bot **si ferma subito** e dice
quale. Le tabelle del database si creano e si aggiornano da sole
all'avvio (`core/migrations/`).

Per aggiornare le dipendenze: si modifica `requirements.txt`, poi
`pip-compile --allow-unsafe --output-file=requirements.lock requirements.txt`.

---

## Configurazione

Tutte le impostazioni stanno nel file `.env` (mai nel repository). Il
modello commentato è [`.env.example`](.env.example).

| Gruppo | Variabili |
|---|---|
| Token dei bot | `YOKAI_BOT_TOKEN`, `YOKAI_CREATOR_TOKEN`, `MUSIC_TOKEN_1`…`5`, `NSFW_TOKEN` (facoltativo finché l'istanza NSFW non esiste) |
| Identità | `OWNER_ID`, `MAIN_GUILD_ID` |
| Ambiente | `ENVIRONMENT` (`development` o `production`, obbligatoria), `LOG_LEVEL` |
| Database | `DATABASE_URL`, `DB_POOL_MIN`, `DB_POOL_MAX` |
| Musica | `LAVALINK_HOST`, `LAVALINK_PORT`, `LAVALINK_PASSWORD`, `LAVALINK_NODES`, `MAIN_RADIO_LOCAL_FOLDER` |
| Servizi esterni | `TWITCH_CLIENT_ID`, `TWITCH_CLIENT_SECRET`, `YOUTUBE_API_KEY`, `PIXABAY_API_KEY` |
| Web e OAuth2 | `WEB_BIND_HOST`, `OAUTH2_CLIENT_ID`, `OAUTH2_CLIENT_SECRET`, `OAUTH2_REDIRECT_URI`, `OAUTH_ENCRYPTION_KEY`, `RESTORE_WEB_PORT`, `ALERTS_WEBHOOK_PORT`, `ALERTS_WEBHOOK_PUBLIC_BASE_URL` |
| Interruttori | `PREMIUM_ALPHA_UNLOCK_ALL`, `ENABLE_EVAL` (spenti di default in produzione) |

**Nel Developer Portal di Discord**, pagina *Bot* del bot principale,
vanno accesi **Server Members Intent** e **Message Content Intent**: il
codice li chiede entrambi e senza non si collega. Sotto i 10.000 utenti
basta l'interruttore; oltre serve una domanda a Discord, da rifare ogni
anno. Per entrare in più di 100 server serve la verifica dell'app.

---

## Test

I test usano un PostgreSQL vero (locale) e oggetti Discord finti ma
fedeli alle firme reali. Non si collegano a Discord.

```bash
pip install -r requirements-dev.txt
export DATABASE_URL="postgresql://<utente>:<password>@127.0.0.1:5432/iyokai_test"

python3 scripts/smoke.py     # smoke mirato: solo i test legati ai file cambiati
python3 -m pytest -q         # suite completa (circa 6 minuti)
```

Lo smoke si usa a gruppo di lavoro chiuso; la suite completa a fine
fase o quando cambiano database, migrazioni o avvio. Le prove che solo
Discord vero può dare sono elencate, passo per passo, in
[`revisione/03-verifica/VERIFICA_LIVE.md`](revisione/03-verifica/VERIFICA_LIVE.md).

---

## Struttura della repository

```
iYokai-DS-BOT/
├── main.py                  avvio di tutti i bot e spegnimento ordinato
├── cogs/                    comandi ed eventi, una cartella per area
│   ├── automod/  fun/  leveling/  logging/  moderation/
│   └── music/  security/  tickets/  utility/  voice_temp/
├── core/                    logica senza Discord, servizi e lavori periodici
│   ├── config.py             legge e controlla il .env
│   ├── database.py           accesso a PostgreSQL
│   ├── premium.py            registro dei moduli e controlli premium
│   ├── repositories/         una classe per tabella o gruppo di tabelle
│   └── migrations/           cambi allo schema, numerati
├── tests/                   test automatici
│   └── support/              oggetti finti fedeli e albero comandi completo
├── scripts/                 smoke test, elenco comandi, simulazione di carico
├── revisione/               specifica (SPEC.md), analisi, piano, regole e prove live
├── .claude/                 regole di lavoro, agenti specializzati, memorie, quaderni (vedi .claude/README.md)
└── COMMAND_LIST.md          elenco dei comandi
```

Per aggiungere un modulo: un file nuovo in `cogs/<area>/`, copiando la
struttura di `cogs/utility/ping.py`. Viene scoperto e caricato da solo.

---

## Come si lavora

- Il lavoro si segue sulle **issue**: etichette per area e tipo, una
  milestone per fase. Niente file di piano.
- Un **orchestratore** coordina agenti specializzati: sviluppatori per
  area, cacciatore di bug, revisore capo, ottimizzatore, guardiano dei
  limiti, sentinella degli aggiornamenti. Ognuno ha i suoi parametri e
  una memoria compressa. La mappa è in
  [`.claude/README.md`](.claude/README.md); lo stato del lavoro in
  [`.claude/memoria/orchestratore.md`](.claude/memoria/orchestratore.md).
- Prima il test che fallisce, poi la modifica. Niente arriva sul ramo
  principale senza revisione e smoke test.
- Un'issue si chiude quando il fix è unito con i suoi test; resta
  l'etichetta `verifica-live` finché non è provato su Discord.
- Le regole complete sono in [`.claude/CLAUDE.md`](.claude/CLAUDE.md).

---

## Documentazione

| Documento | Contenuto |
|---|---|
| [`revisione/SPEC.md`](revisione/SPEC.md) | Specifica completa e stato di ogni voce |
| [`COMMAND_LIST.md`](COMMAND_LIST.md) | Tutti i comandi |
| [`revisione/README.md`](revisione/README.md) | Indice dell'analisi |
| [`revisione/01-analisi/REVIEW.md`](revisione/01-analisi/REVIEW.md) | Problemi trovati nel codice |
| [`revisione/01-analisi/LIMITI.md`](revisione/01-analisi/LIMITI.md) | Limiti di Discord e delle librerie, lista di controllo |
| [`revisione/01-analisi/CONFRONTO_BOT.md`](revisione/01-analisi/CONFRONTO_BOT.md) | Confronto con gli altri bot |
| [`revisione/01-analisi/catalogo/`](revisione/01-analisi/catalogo/README.md) | Catalogo voce per voce delle funzioni che gli altri bot hanno e iYokai no (1.452 voci) |
| [`revisione/01-analisi/APP_UTENTE_E_DESKTOP.md`](revisione/01-analisi/APP_UTENTE_E_DESKTOP.md) | Funzioni possibili senza il bot nel server e da PC |
| [`revisione/02-piano/DECISIONI.md`](revisione/02-piano/DECISIONI.md) | Decisioni prese |
| [`revisione/02-piano/MODIFICHE_ESISTENTE.md`](revisione/02-piano/MODIFICHE_ESISTENTE.md) | Cosa cambiare in ciò che esiste |
| [`revisione/02-piano/NUOVE_FUNZIONI.md`](revisione/02-piano/NUOVE_FUNZIONI.md) | Funzioni da aggiungere |

---

## Sicurezza e privacy

- Nessun segreto nel repository: token, password e chiavi stanno solo
  nel `.env`, che non viene mai salvato in git.
- I token OAuth degli utenti sono cifrati nel database.
- I dati di un server vengono cancellati 90 giorni dopo l'uscita del
  bot (in arrivo con la fase F5), salvo i ban e i kick di sicurezza.
- Una vulnerabilità si segnala in privato all'owner, non con una issue
  pubblica.
