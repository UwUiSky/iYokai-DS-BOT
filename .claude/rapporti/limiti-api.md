# Quaderno dei limiti e delle API

Il riferimento completo dei limiti è
`revisione/01-analisi/LIMITI.md`. Qui stanno i rilievi nuovi.

## Parte A — Limiti superati o ignorati

| Data | Dove | Limite | Numero | Cosa cambiare | Stato |
|---|---|---|---|---|---|
| 05/10 | `core/restore_orchestrator.py` (`/restore-users`) | Chiamate dirette con `aiohttp`: saltano la gestione dei limiti di frequenza di discord.py | 50 richieste al secondo; blocco dell'IP a 10.000 errori in 10 minuti | Passare da `bot.http.request(Route(...))` | aperto (in #68) |
| 05/10 | `cogs/automod/automod.py` | Liste dei link senza tetto | embed 4096, menu 25 | Tetto alle voci e pagine | issue #133 |

## Parte B — Cosa l'API di Discord permette e discord.py no

Regola: la chiamata diretta sta in `core/discord_raw.py`, passa da
`bot.http.request(Route(...))`, ha un test e la nota "togliere quando
discord.py lo offre".

| Funzione | Cosa serve dall'API | discord.py 2.7.1 | Come farla oggi | Controllato il | Stato |
|---|---|---|---|---|---|
| Inviare un messaggio vocale | Messaggio con il segno "vocale" e un allegato audio con durata e forma d'onda | Li legge (`Message.is_voice_message`), non li invia | Chiamata diretta | 05/10/2026, sul codice installato | issue #142, in attesa dell'owner |

Da controllare al prossimo giro: cos'altro è nel registro delle
modifiche dell'API e manca in discord.py 2.7.1.
