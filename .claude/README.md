# .claude/ — Il punto di riferimento per lavorare su iYokai

Qui c'è tutto ciò che serve a una sessione di lavoro, con Opus o con
Sonnet: chi fa cosa, con quali regole, e cosa è già stato fatto.

```
.claude/
  CLAUDE.md        le regole del progetto (caricato da solo a ogni sessione)
  README.md        questa mappa
  regole/
    COMUNI.md      regole valide per tutti: pochi token, memoria, come fermarsi
  agents/          le ISTRUZIONI di ogni agente, con i suoi parametri (non cambiano mentre si lavora)
  memoria/         la MEMORIA COMPRESSA di ogni agente, un file a testa (cambia a ogni voce chiusa)
  rapporti/        i quaderni dei rilievi degli agenti di controllo
```

## Come si usa

1. La sessione principale è l'**orchestratore**: legge
   `memoria/orchestratore.md` e le issue, e decide il giro.
2. Per ogni lavoro prepara una **scheda** breve e lancia l'agente
   giusto. L'agente legge `regole/COMUNI.md`, la **sua** memoria e la
   scheda: non rilegge il progetto.
3. A ogni voce chiusa l'agente aggiorna la sua memoria. Prima di
   fermarsi la salva sempre, con il prossimo passo esatto.
4. La volta dopo riparte da lì.

## Lavorare con Sonnet (per consumare meno)

Tutta la struttura funziona con **Sonnet come modello della sessione**.
Nessun agente è legato a Opus.

**Per iniziare una sessione** basta scrivere: *"Riprendi il lavoro"*.
`CLAUDE.md` viene caricato da solo; l'orchestratore legge
`memoria/orchestratore.md` e parte dal primo punto della coda.

**Regole in più quando l'orchestratore è Sonnet:**
1. Un gruppo piccolo alla volta: **1 o 2 agenti**, non 3; da 3 a 4 voci
   per agente.
2. La scheda la scrive copiando dalla issue: numero, voci, file. Non la
   inventa e non rilegge il progetto per scriverla.
3. **Mai saltare i controlli**: `guardiano-limiti` prima di ogni
   comando o interfaccia nuovi; `cacciatore-bug` e `revisore-capo` su
   ogni ramo oltre le 30 righe. Con Sonnet contano di più.
4. Se una prova fallisce tre volte, si ferma, scrive in memoria cosa ha
   provato e lo dice all'owner. Non insiste.
5. A fine sessione aggiorna `memoria/orchestratore.md`, fa commit e
   push. Anche se la sessione è stata corta.

**Quando conviene accendere Opus** (poche volte, per poco):
- una decisione di architettura nuova (per esempio dividere i compiti
  tra il bot principale e iYokai Mod);
- un bug che ha resistito a tre tentativi;
- la revisione di un cambio grosso su database, sicurezza o avvio: si
  mette `model: opus` nel solo `agents/revisore-capo.md`, si fa la
  revisione, si rimette `inherit`;
- la fine di una fase, per il giro di controllo completo.

Per tutto il resto (voci di F1, correzioni, test, funzioni con la
scheda già scritta) Sonnet basta.

## Gli agenti

### Coordinamento

| Agente | Compito | Modello |
|---|---|---|
| `orchestratore` | Sceglie il lavoro, prepara le schede, unisce, pubblica, tiene le issue | quello della sessione |

### Controllo (non scrivono il codice del bot)

| Agente | Compito | Quando | Quaderno | Modello |
|---|---|---|---|---|
| `guardiano-limiti` | Limiti di Discord, delle librerie e dei servizi; cosa l'API permette e discord.py no | **Prima** di scrivere un comando o un'interfaccia; dopo, sul diff | `rapporti/limiti-api.md` | quello della sessione |
| `cacciatore-bug` | Trova i difetti veri e li dimostra | Dopo ogni gruppo di modifiche | `rapporti/bug.md` | quello della sessione |
| `revisore-capo` | Ultimo controllo riga per riga prima di `main` | Dopo il cacciatore | `rapporti/revisione.md` | quello della sessione |
| `ottimizzatore` | Memoria, processore, disco, database, cache | Sui diff con cicli, cache, immagini, query; a fine fase | `rapporti/ottimizzazione.md` | quello della sessione |
| `sentinella-aggiornamenti` | Versioni nuove di librerie e API, e cosa cambia per il bot | Due volte al mese: 1° e 15 (attività programmata) | `rapporti/aggiornamenti.md`, issue #143 | sonnet |

### Sviluppo, per area (scrivono codice e test solo nella loro area)

| Agente | Area | Cartelle | Fasi |
|---|---|---|---|
| `dev-moderazione` | Moderazione, AutoMod, sicurezza, verifica | `cogs/moderation`, `automod`, `security` | F1, F7, F9 |
| `dev-log-ticket` | Log, ticket, modmail, vocali temporanei | `cogs/logging`, `tickets`, `voice_temp` | F1, F6, F9 |
| `dev-musica` | Musica, radio, i 5 bot musicali | `cogs/music` | F2 |
| `dev-backup` | Backup, ripristino, Creator, iYokai Mod, whitelabel | `cogs/utility/backup*`, `restore.py` | F3 |
| `dev-economia` | Livelli, economia, clan, giochi | `cogs/leveling`, `fun` | F1, F9, F13 |
| `dev-utilita` | Utilità, avvisi, benvenuto, ruoli, NSFW | `cogs/utility` (il resto), `nsfw` | F1, F9, F11, F13 |
| `dev-core` | Avvio, database, migrazioni, configurazione, owner, comandi, lingue | `main.py`, `core/` di base | F1, F5, F7, F8 |
| `custode-ai` | Snodo AI: scelta del servizio, quote, chiavi, cache | `core/ai_*` | F12 |
| `dev-ai` | Funzioni AI visibili agli utenti | `cogs/ai` | F12 |
| `dev-web` | Pannello web, app utente, programma per PC | `cogs/user_app`, `core/panel_bridge.py` | F10, F13 |

Gli agenti di sviluppo usano `sonnet`.

## I parametri di un agente

Stanno in due punti del suo file in `agents/`:

- **In testa** (tra le righe `---`): `name`, `description` (quando
  usarlo), `tools` (cosa può usare), `model` (`opus`, `sonnet`,
  `inherit` = quello della sessione). Per cambiare modello a un agente
  si cambia quella riga.
- **Nella tabella "Parametri"**: memoria, quaderno, file suoi e non
  suoi, issue, fase, dove trovare il dettaglio, test, database.

## Ordine dei controlli su ogni lavoro

```
disegno → guardiano-limiti → agente di area (codice + test)
        → cacciatore-bug → revisore-capo → (ottimizzatore) → smoke → main
```

Per i fix piccoli (fino a 30 righe, niente dati né sicurezza) basta la
lettura del diff da parte dell'orchestratore.

## Perché costa meno token

- Un agente legge **tre file corti** all'avvio, non il progetto.
- Ogni agente conosce già le trappole della sua area (sono nelle sue
  istruzioni e nella sua memoria).
- I controlli lavorano sul **diff**, non su tutto il codice.
- Ciò che si può controllare con un test si controlla con un test.
- Nessun agente obbliga a usare Opus: lo sviluppo gira su `sonnet`, i
  controlli sul modello della sessione.
- Chi riprende un lavoro legge il "prossimo passo", non ricostruisce.

## Aggiungere un agente

1. `agents/<nome>.md`: testa, tabella dei parametri, istruzioni (entro
   90 righe).
2. `memoria/<nome>.md` dal modello `memoria/_MODELLO.md`.
3. Una riga in questa mappa.
