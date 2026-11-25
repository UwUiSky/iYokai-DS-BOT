# Servizio di sistema di iYokai

Il bot parte all'avvio della macchina e si rialza da solo se cade (Debian e Ubuntu, x86_64 e arm64).

## Installazione

1. Prepara il bot in `/opt/iyokai` (clone, `.env`, `.venv`), come in `avvia.sh`.
2. Lancia come amministratore: `sudo scripts/installa_servizio.sh` (con `--prova` mostra cosa farebbe senza toccare niente).
   Lo script crea l'utente `iyokai`, le cartelle `logs/` e `data/`, copia `iyokai-bot.service` in `/etc/systemd/system/`,
   lo accende all'avvio e lo fa partire.
3. Controlla: `systemctl status iyokai-bot` e `curl -s http://127.0.0.1:8424/salute`.

## Cosa fa il servizio

- `Restart=always`: si rialza dopo qualsiasi caduta. L'attesa cresce da 5 secondi a 5 minuti (systemd 254 o più).
- Dopo 20 partenze fallite in 15 minuti systemd si ferma (`StartLimit`): serve guardare i log (`journalctl -u iyokai-bot -e`).
- `TimeoutStopSec=75`: se lo spegnimento si blocca, systemd chiude il processo.
- `MemoryHigh=3G`, `MemoryMax=4G`: tetti di memoria; adattali ai tuoi numeri.
- PostgreSQL: il servizio parte dopo `postgresql.service` se è sulla stessa macchina.
- **Lavalink è facoltativo.** Senza Lavalink il bot parte lo stesso (moderazione, ticket e il resto funzionano); la musica si
  riattiva da sola appena Lavalink risponde. Lavalink con Docker: `deploy/lavalink/README.md`.

## `/salute`

`http://127.0.0.1:8424/salute` (porta `SALUTE_PORT`, `0` la spegne; ascolta solo su `WEB_BIND_HOST`). Risponde:

- `200` con `stato: ok` o `degradato` (qualche giro periodico sbaglia da più volte di fila);
- `503` con `stato: giu` se il bot non è pronto o il database non risponde entro 2 secondi.

Nel JSON: bot pronto, tempo del database, giri periodici vivi e in difficoltà, ritardo del ciclo asyncio (ultimo e massimo
degli ultimi 5 minuti), stato di Lavalink e dei bot musicali. Nessun segreto. Ogni 5 minuti le stesse misure vanno nel log.

## Avvisi

Il bot scrive all'owner in DM quando un servizio cade (un giro che sbaglia 3 volte di fila, un bot secondario, Lavalink che
resta giù più di 2 minuti) e quando torna. I messaggi sono raggruppati e distanziati di almeno 5 minuti.
