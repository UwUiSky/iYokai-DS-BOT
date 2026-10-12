# Musica: Lavalink, nodi pubblici e documentazione

I nodi pubblici scelti dal bot **non sono una fonte di verita'**: sono una
scelta operativa che cambia nel tempo. Nel codice non ce n'e' nessuno: si
mettono nel `.env` (`LAVALINK_NODES`). Per produzione, file locali e radio
propria serve un Lavalink tuo (`deploy/lavalink/`).

## Documentazione ufficiale

| Cosa | Dove |
|---|---|
| Lavalink v4 e sistema dei plugin | https://lavalink.dev/ |
| Plugin YouTube | https://github.com/lavalink-devs/youtube-source |
| LavaSrc (Spotify, Apple Music, Deezer) | https://github.com/topi314/LavaSrc |
| Elenchi di nodi della comunita' | https://lavalink.darrennathanael.com/ |
| Client Python usato dal bot | documentazione del pacchetto `wavelink` |

## Leggere cosa sa fare un nodo (`/v4/info`)

```bash
curl -s -H "Authorization: <password>" https://<nodo>/v4/info
```

- `version.semver`: deve essere **4.2.0 o successiva**. Il bot controlla
  da solo all'avvio e scarta i nodi piu' vecchi con un avviso nei log.
- `sourceManagers`: le sorgenti attive (`youtube`, `spotify`, `local`...).
  Un nodo pubblico che dichiara una sorgente non e' detto che la regga:
  provala con un `/music play`.
- `plugins`: nomi e versioni dei plugin installati.

## Controllo periodico dei nodi

```bash
python3 scripts/check_lavalink_nodes.py          # legge LAVALINK_NODES dal .env
python3 scripts/check_lavalink_nodes.py --strict # esce con errore se un nodo e' morto o vecchio
```

Scrive un WARNING per ogni nodo che non risponde, con password sbagliata o
sotto la 4.2.0. Utile in una CI o in un cron settimanale.

## Self-host

Guida, `docker-compose.yml` e `application.yml` (solo segnaposto) in
`deploy/lavalink/`. NodeLink (PerformanC) e' compatibile con l'API di
Lavalink: si aggiunge in `LAVALINK_NODES` come qualunque altro nodo.
