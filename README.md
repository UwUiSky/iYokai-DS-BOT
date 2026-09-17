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

**Fase attuale:** `0 — Fondamenta` (core system, database, premium framework)

---

## 🏗️ Architettura

Il progetto non è un solo bot, ma un piccolo ecosistema di applicazioni
Discord separate, ciascuna con il proprio token e il proprio scopo:

| Applicazione | Ruolo |
|---|---|
| **iYokai Main** | Il core: moderazione, automod, security, ticket, vocali temporanei, livelli, gilde, log, utility *(questa repo)* |
| **iYokai Creator** | Crea e cede i server di backup, resta sempre sotto i 10 server |
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
├── main.py                    # Entry point — AutoShardedBot
├── core/
│   ├── config.py               # Legge e valida .env — TUTTA la config passa da qui
│   ├── database.py              # Layer unico di accesso a PostgreSQL (asyncpg)
│   ├── premium.py                # Sistema premium: registry + decorator, tutto spento di default
│   └── cog_manager.py             # Scopre e carica automaticamente i cog
├── cogs/
│   ├── moderation/                 # (vuoto, in arrivo)
│   ├── security/                    # (vuoto, in arrivo)
│   ├── leveling/                     # (vuoto, in arrivo — XP, economy, gilde)
│   ├── tickets/                       # (vuoto, in arrivo)
│   ├── voice_temp/                     # (vuoto, in arrivo)
│   └── utility/
│       ├── ping.py                      # 📖 MODELLO — copialo per ogni nuovo cog
│       └── owner_premium.py              # /owner premium-list, premium-toggle, whitelist
├── .env.example                          # Template — SI committa
├── .env                                   # Valori veri — NON si committa MAI
├── SPEC.md                                  # FONTE DI VERITÀ: specifica completa + stato di ogni voce
├── PROGRESS.md                             # Cronologia, decisioni tecniche, bug noti
└── requirements.txt
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

# 3. Dipendenze
pip install -r requirements.txt

# 4. Configurazione
cp .env.example .env
nano .env                       # compila TUTTI i valori richiesti

# 5. Avvio
python main.py
```

Se manca una variabile obbligatoria in `.env`, il bot **si ferma subito
all'avvio** con un messaggio che dice esattamente quale variabile manca
— non parte "a metà" con qualcosa di rotto.

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
