# Catalogo delle funzioni mancanti

Ogni riga dei file qui sotto è **una funzione o un comando** che uno dei
bot confrontati ha e iYokai non ha (❌) oppure ha solo in parte (🟡).
Le funzioni che iYokai ha già per intero non sono elencate.

Come leggere una riga: codice · funzione · chi ce l'ha (con la fonte) ·
com'è oggi in iYokai · come farla in iYokai (gruppo di comandi, limiti
da rispettare) · scheda del piano a cui appartiene (`NF-xx`, `M x.y`) o
"nuova" se non era ancora in nessun piano.

## I numeri (contati sulle righe, non stimati)

| File | Area | Voci | ❌ mancano | 🟡 parziali | Non ancora in un piano |
|---|---|---|---|---|---|
| [`01-moderazione.md`](01-moderazione.md) | Moderazione | 116 | 95 | 21 | 91 |
| [`02-automod.md`](02-automod.md) | AutoMod | 75 | 60 | 15 | 70 |
| [`03-sicurezza-antiraid-antinuke.md`](03-sicurezza-antiraid-antinuke.md) | Sicurezza: anti-nuke, anti-raid, filtri all'ingresso, canale trappola | 46 | 33 | 13 | 32 |
| [`04-verifica.md`](04-verifica.md) | Verifica dei nuovi membri | 31 | 28 | 3 | 15 |
| [`05-log.md`](05-log.md) | Log | 30 | 27 | 3 | 15 |
| [`06-ticket-e-modmail.md`](06-ticket-e-modmail.md) | Ticket e ticket via messaggio privato (ModMail) | 88 | 76 | 12 | 57 |
| [`07-backup-e-restore.md`](07-backup-e-restore.md) | Backup e restore | 41 | 38 | 3 | 17 |
| [`08-configurazione-pannello-premium.md`](08-configurazione-pannello-premium.md) | Configurazione, pannello, permessi, premium, lingue, marchio | 46 | 39 | 7 | 23 |
| [`09-benvenuto-e-ruoli.md`](09-benvenuto-e-ruoli.md) | Benvenuto e ruoli | 113 | 101 | 12 | 77 |
| [`10-livelli-e-rank.md`](10-livelli-e-rank.md) | Livelli e rank | 91 | 81 | 10 | 56 |
| [`11-economia-e-giochi.md`](11-economia-e-giochi.md) | Economia e giochi | 161 | 145 | 16 | 51 |
| [`12-musica.md`](12-musica.md) | Musica | 90 | 81 | 9 | 55 |
| [`13-vocali-temporanei.md`](13-vocali-temporanei.md) | Vocali temporanei | 21 | 16 | 5 | 18 |
| [`14-utility.md`](14-utility.md) | Utility | 229 | 209 | 20 | 160 |
| [`15-alert-social.md`](15-alert-social.md) | Alert social | 49 | 36 | 13 | 33 |
| [`16-statistiche.md`](16-statistiche.md) | Statistiche | 61 | 55 | 6 | 27 |
| [`17-divertimento-e-immagini.md`](17-divertimento-e-immagini.md) | Divertimento e immagini | 139 | 127 | 12 | 127 |
| [`18-ai.md`](18-ai.md) | AI | 25 | 25 | 0 | 15 |
| | **Totale** | **1452** | **1272** | **180** | **939** |

## Cosa dicono questi numeri

- Le voci sono **1452**, contando a livello di singolo comando o
  singola opzione. Molte sono varianti piccole della stessa funzione
  (per esempio i tanti giochi e comandi immagine di Dank Memer,
  NadekoBot e Yggdrasil).
- Il numero **non** è quello di funzioni "grandi" mancanti: quelle sono
  le 41 schede `NF` di `../../02-piano/NUOVE_FUNZIONI.md`.
- **939** voci non erano in nessun piano: vanno aggiunte alla scheda
  `NF` più vicina o diventano issue nuove, area per area.
- In `12-musica.md` alcune voci sono segnate "scelta dell'owner: no"
  (ruolo DJ, voto per saltare, filtri…): restano elencate perché gli
  altri bot le hanno, ma l'owner le aveva escluse. Basta dirlo per
  rimetterle in piano.

## Fonti e limiti

- Ogni file ha in fondo le sue fonti. "(terzi)" = il dato viene da un
  sito esterno e non dal bot; "(non verificato)" = nessuna fonte
  ufficiale leggibile.
- Non è stato possibile leggere le pagine ufficiali di Dyno, Sapphire,
  Maki, Atlas, RestoreCord, Hydra e in parte Jockie, Dank Memer,
  UnbelievaBoat e Tatsu (pagine che si aprono solo con un browser
  vero). Per questi bot l'elenco può essere incompleto.
- Le idee prese da Nighty sono solo quelle realizzabili in modo
  regolare: vedi `../APP_UTENTE_E_DESKTOP.md`.
- Questo catalogo guarda solo **gli altri bot**. Le funzioni AI di cui
  si è parlato con l'owner e con le altre AI (comprese le 25 righe di
  `18-ai.md`) sono tutte in [`../FUNZIONI_AI.md`](../FUNZIONI_AI.md); le
  funzioni non AI discusse e assenti da ogni lista sono in
  [`../VOCI_OMESSE.md`](../VOCI_OMESSE.md).
