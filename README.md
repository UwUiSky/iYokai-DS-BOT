<div align="center">

# 😻 iYokai

**Bot Discord multi-tenant in Python — moderazione, sicurezza, economia, gilde e molto altro**

*Repository privata — in sviluppo*

</div>

---

## 📌 Stato del progetto

> Lo stato dettagliato, aggiornato ad ogni sessione di lavoro, vive in
> **[`SPEC.md`](SPEC.md)** — la specifica completa, foglia per foglia,
> con lo stato reale di ogni singola voce. **È la fonte di verità del
> progetto**: ogni sessione di lavoro parte da qui.
>
> **[`PROGRESS.md`](PROGRESS.md)** — cronologia di cosa è stato fatto,
> decisioni tecniche vincolanti e bug noti da non reintrodurre.
>
> **[`BACKLOG.md`](BACKLOG.md)** — proposte esterne (altre AI, idee
> future) valutate una per una con un verdetto esplicito. Niente
> entra in `SPEC.md` senza passare prima da qui.
>
> **[`revisione/README.md`](revisione/README.md)** — la revisione del
> codice: analisi, limiti di Discord, confronto con gli altri bot,
> **piano di lavoro in ordine**, decisioni prese e prove da fare su
> Discord vero. Chi deve lavorare sul bot parte da lì.

**Fase attuale (04/10/2026):** correzione. Il bot non è ancora in
nessun server. La lista di lavoro è
[`revisione/02-piano/PRIORITA.md`](revisione/02-piano/PRIORITA.md).

---

## 🏗️ Architettura

Il progetto non è un solo bot, ma un piccolo ecosistema di applicazioni
Discord separate, ciascuna con il proprio token e il proprio scopo:

| Applicazione | Ruolo |
|---|---|
| **iYokai Main** | Il core: moderazione, automod, security, ticket, vocali temporanei, livelli, gilde, log, utility *(questa repo)* |
| ~~iYokai Creator~~ | **Non serve più.** Discord non lascia più creare server ai bot. Il backup viene rifatto senza Creator (decisione D8); il suo token resta obbligatorio nel `.env` solo finché il codice non viene tolto (fase F3) |
| **iYokai Music** ×5 | Cinque istanze, una connessione vocale ciascuna |
| **iYokai NSFW** | Modulo R34/NSFW isolato dal core |
| **iYokai Desktop** | Presence personalizzata via RPC locale, nessun user token |
| **iYokai Panel** | Web panel per verify avanzato e OAuth2 |

> Per il ragionamento completo dietro queste scelte (limiti reali
> dell'API Discord, cosa è fattibile e cosa no, GDPR, ecc.) vedi lo
> schema tecnico di progetto discusso in chat.

---

## 📁 Struttura di questa repository

```
iYokai-DS-BOT/
├── main.py                 # Avvio: bot principale + 5 bot musicali (+ Creator, da togliere)
├── core/                   # Logica senza Discord, servizi, worker
│   ├── config.py            # Legge e valida .env — TUTTA la config passa da qui
│   ├── database.py           # Accesso a PostgreSQL (asyncpg)
│   ├── premium.py             # Sistema premium: registro dei moduli e controlli
│   ├── cog_manager.py          # Scopre e carica da solo i cog
│   ├── repositories/           # Una classe per tabella o gruppo di tabelle
│   └── migrations/             # Cambi allo schema, numerati (0001, 0002…)
├── cogs/                   # Comandi e ascolto degli eventi, per area
│   ├── automod/  fun/  leveling/  logging/  moderation/
│   ├── music/  security/  tickets/  voice_temp/
│   └── utility/             # ping.py è il MODELLO da copiare per un cog nuovo
├── tests/                  # Test automatici (serve un PostgreSQL locale)
├── scripts/                # Script di servizio (es. elenco comandi)
├── revisione/              # Revisione del codice e piano di lavoro
│   ├── README.md            # Indice: da dove partire
│   ├── 01-analisi/          # REVIEW.md, LIMITI.md, CONFRONTO_BOT.md
│   ├── 02-piano/            # PRIORITA.md, MODIFICHE_ESISTENTE.md, NUOVE_FUNZIONI.md, DECISIONI.md
│   ├── 03-verifica/         # VERIFICA_LIVE.md
│   └── archivio/            # Documenti vecchi, tenuti come storico
├── .env.example            # Modello — SI committa
├── .env                    # Valori veri — NON si committa MAI
├── CLAUDE.md               # Istruzioni per chi lavora sul repository
├── CLAUDE_MANDATORY_TEST_RULES.md  # Regole su segreti e test live
├── SPEC.md                 # FONTE DI VERITÀ: cosa deve fare il bot e stato di ogni voce
├── COMMAND_LIST.md         # Elenco dei comandi, generato dall'albero vero
├── BACKLOG.md              # Proposte esterne valutate
├── PROGRESS.md             # Cronologia e decisioni tecniche
├── requirements.txt        # Dipendenze dirette
└── requirements.lock       # Versioni esatte (pip-compile)
```

---

## ⚙️ Setup locale / sul server

```bash
# 1. Clona il repository
git clone https://github.com/UwUiSky/iYokai-DS-BOT.git
cd iYokai-DS-BOT

# 2. Ambiente virtuale
python3 -m venv venv
source venv/bin/activate        # su Windows: venv\Scripts\activate

# 3. Dipendenze — usa requirements.lock (versioni esatte, riproducibili),
# non requirements.txt direttamente (SEC-15). Per rigenerare il lock
# dopo aver cambiato requirements.txt:
#   pip install pip-tools
#   pip-compile --allow-unsafe --output-file=requirements.lock requirements.txt
pip install -r requirements.lock

# 4. Configurazione
cp .env.example .env
nano .env                       # compila TUTTI i valori richiesti

# 5. Avvio
python main.py
```

Se manca una variabile obbligatoria in `.env`, il bot **si ferma subito
all'avvio** con un messaggio che dice esattamente quale variabile manca
— non parte "a metà" con qualcosa di rotto.

Tre cose da sapere prima del primo avvio:

- **`ENVIRONMENT`** è obbligatoria e accetta solo `development` o
  `production`.
- **Intent privilegiati.** Nel Developer Portal di Discord, pagina
  *Bot* del bot principale, vanno accesi **Server Members Intent** e
  **Message Content Intent**. Il codice li chiede entrambi: se uno è
  spento il bot non riesce a collegarsi. Sotto i 10.000 utenti basta
  l'interruttore; da 10.000 serve una domanda a Discord, da rifare ogni
  anno.
- **Verifica dell'app.** Per entrare in più di 100 server Discord
  chiede la verifica dell'applicazione (privacy policy, identità, 2FA).

---

## ➕ Aggiungere un nuovo modulo (cog)

1. Crea un file nella sottocartella pertinente, es. `cogs/moderation/ban.py`
2. Copia la struttura da **`cogs/utility/ping.py`** — è commentato
   apposta per essere il modello di riferimento
3. Nessuna registrazione manuale altrove: il cog manager lo scopre e lo
   carica da solo al prossimo avvio

---

## 🧪 Test

I test coprono la logica pura (permessi, calcoli) e il database reale
(query eseguite davvero contro un PostgreSQL locale, non un mock).
**Non** coprono la connessione a Discord — quella si verifica sul
server di test, non nei test automatici.

```bash
pip install -r requirements-dev.txt

# Serve un PostgreSQL locale raggiungibile. Il modo più rapido:
# un database vuoto chiamato "iyokai_test" su un'istanza Postgres
# qualsiasi, poi:
export DATABASE_URL="postgresql://<utente>:<password>@127.0.0.1:5432/iyokai_test"

pytest tests/ -v
```

`tests/conftest.py` imposta automaticamente tutte le altre variabili
richieste da `core/config.py` con valori fittizi (i token Discord non
servono per questi test): solo `DATABASE_URL` deve puntare a un
database vero.

---

## 🔒 Sicurezza sul server di produzione

- Il processo gira come utente Linux **dedicato, non root**
- `.env` con permessi `600`
- PostgreSQL accetta connessioni **solo da `127.0.0.1`**
- Il codice sorgente resta **leggibile e commentato**: la protezione sta
  nei permessi del sistema, non nell'offuscamento — un `.pyc` o un
  eseguibile impacchettato si decompilano comunque in minuti, quindi
  non aggiungono sicurezza reale, solo attrito

---

## 💎 Sistema Premium

Ogni modulo è **predisposto** per diventare a pagamento, ma **parte
gratuito per tutti** (`is_premium_active = False` di default). Solo il
proprietario del bot può accendere la flag premium di un modulo, tramite
`/owner premium-toggle` — da quel momento in poi quel modulo richiede
sblocco per tutti i server eccetto quelli in whitelist manuale.

Vedi `core/premium.py` per il funzionamento completo, commentato riga
per riga.
