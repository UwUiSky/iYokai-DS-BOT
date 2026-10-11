# Registro delle issue risolte

Una riga per issue chiusa: cosa non andava e come è stato sistemato.
Si aggiorna a ogni issue chiusa, insieme al commento su GitHub (CLAUDE.md).
Le prove ancora da fare su Discord restano in `03-verifica/VERIFICA_LIVE.md`.

| Issue | Problema | Come è stato sistemato | Commit | Data |
|---|---|---|---|---|
| #137 | Il messaggio privato di kick/ban partiva dopo l'azione e non arrivava | Il DM parte prima di kick, ban, tempban, softban (`try_dm_message`); se non arriva lo dice nella risposta | f0e2056 | 06/10 |
| #133 | Problemi di sicurezza del giro del 05/10 | Correzioni in anti-raid, anti-nuke, verifica (cache a versione); benvenuto privato sospeso durante un raid | f045c97 | 06/10 |
| #135 | Scritture non sicure su clan e premium | Operazioni atomiche in `guild_clan_repo` (ordine dei blocchi membro → monete → clan) | 1bc7ab1 | 06/10 |
| #136 | `/config export` scriveva `null` rifiutati da `/config import` | Export e import allineati sui valori nulli | 1bc7ab1 | 06/10 |
| #134 | Vocali temporanei e ticket: problemi del giro del 05/10 | Correzioni su vocali temporanei, ticket e log avanzati premium | a3004ee | 06/10 |
| #144 | `/voice kick` senza controllo di gerarchia; unlock azzerava Connetti | Controllo di gerarchia nel kick; unlock ripristina Connetti; memoria del valore con tetto di 5.000 canali | c0e0a0d | 06/10 |
| #146 | Boost clan: un solo tipo, acquisti sovrapposti | Tre tipi (exp, coin, super), niente acquisti sovrapposti dello stesso beneficio (D23, migrazione 0020) | aaf4ea2 | 07/10 |
| #76, #3, #24, #31, #40 | Struttura dei comandi: limite di 100 comandi di primo livello | F7 (D24): 16 gruppi + `-cerca-comando` e `-chiedi`, accesso per ruolo, `/owner` solo nel server owner, sync con hash | d477200 | 11/10 |

## Parziali (issue ancora aperte, voci già fatte)

- #147: pannello di `-cerca-comando`, ricerca, `-chiedi`, `command_usage` (0022). Mancano `scripts/genera_wiki.py` (F10) e l'AI (F12).
- #67: voci 11.1–11.10 (Twitch, YouTube, feed, rete). Mancano 11.11 (F5) e 11.12 (F13).
