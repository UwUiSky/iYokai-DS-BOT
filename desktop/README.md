# iYokai Desktop

Programma per PC di iYokai (SPEC D.1-D.11, #108). Solo Python 3.11 o più nuovo, nessuna libreria da installare.

## Cosa fa

| Voce | Comando | Come |
|---|---|---|
| D.1 Collegamento | `collega` | Codice personale creato dal comando dell'app iYokai (`/desktop collega`). Il servizio conserva solo l'impronta. |
| D.2 Stato (rich presence) | `presenza` | Canale locale (IPC) del client Discord. Testi, immagini, 2 bottoni, timer. |
| D.3 Rotazione | `rotazione a b c --ogni 30` | Minimo 20 secondi (limite di Discord). |
| D.4 Profili | `profilo salva\|elenco\|elimina` | File sul PC. |
| D.5 Notifiche | `avvisi` | Menzioni, risposte, parole chiave, promemoria, assistenza. Si accendono con `/desktop avvisi`. |
| D.6 Storico menzioni | `menzioni [--apri N]` | Salto al messaggio con il link di Discord. |
| D.7 Storico comandi e azioni | `storico` | I tuoi comandi (se hai acceso lo storico) e le azioni del bot per te. |
| D.8 Traduzione e testi pronti | `traduci`, `traduci-appunti`, `incolla NOME` | Il testo tradotto va negli appunti: lo incolli tu. |
| D.9 Pannello staff | `staff blocca\|sblocca\|timeout\|annuncio\|azioni` | Lo fa il bot, con i tuoi permessi veri nel server. |
| D.10 I miei server | `server` | I server dove c'è iYokai, quelli dove sei staff, link al pannello. |
| D.11 Approvazione di Discord | `avanzate` | Notifiche del client e controllo della voce: spente, «da attivare». |

## Primo avvio

1. `python -m iyokai_desktop configura --servizio https://INDIRIZZO_DEL_PANNELLO --app-id ID_APPLICAZIONE`
   L'ID è quello dell'applicazione Discord della rich presence (Developer Portal). Le immagini dello stato si
   caricano lì in «Rich Presence > Art Assets».
2. Nell'app iYokai: `/desktop collega` (il codice si vede una volta). Poi `python -m iyokai_desktop collega`.
3. Per le notifiche: `/desktop avvisi` con acceso, `/desktop parole` per le parole chiave.

Si avvia dalla cartella `desktop/`.

## Tasto rapido per la traduzione

Il programma non ascolta la tastiera. Si assegna una scorciatoia del sistema al comando `traduci-appunti`:
Windows (collegamento con «Tasto di scelta rapida»), macOS (Automazioni rapide), Linux (scorciatoie del desktop).
Copi il testo, premi il tasto, incolli la traduzione.

## Regole

- Nessun uso del token dell'account Discord e nessuna azione a nome tuo (Discord lo vieta).
- Il codice personale sta in `codice.txt` nella cartella delle impostazioni (accesso solo tuo); nessun segreto nel programma.
- Il servizio si raggiunge solo in https (http solo su localhost).
- Il salto al messaggio apre solo link `https://discord.com/channels/...`.

## Prove

Dalla cartella principale del progetto: `python3 -m pytest -q tests/test_desktop_prog_*.py`.
