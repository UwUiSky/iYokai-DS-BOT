# Lavalink proprio per iYokai

Serve per tre cose che i nodi pubblici non fanno:

1. **Gli inediti della radio** (`/owner radio add-local`): un nodo pubblico
   non legge il disco di questa macchina.
2. **Spotify** (plugin LavaSrc, con le tue chiavi) e YouTube (plugin).
3. **Stabilita'**: i nodi pubblici nascono, muoiono e hanno limiti.

Requisiti: Docker, **Lavalink 4.2.0 o successivo** (cifratura vocale DAVE,
obbligatoria da 01/03/2026; i nodi piu' vecchi il bot li scarta
all'avvio con un avviso), `wavelink>=3.5.1`.

## Avvio

```bash
cd deploy/lavalink
export LAVALINK_PASSWORD='una-password-lunga'      # la stessa del .env del bot
export MAIN_RADIO_LOCAL_FOLDER=/percorso/inediti   # facoltativo
export SPOTIFY_CLIENT_ID=... SPOTIFY_CLIENT_SECRET=...   # facoltativi: poi `spotify: true` in application.yml
docker compose up -d
docker compose logs -f lavalink    # al primo avvio scarica i plugin
```

Nel `.env` del bot:

```
LAVALINK_HOST=127.0.0.1
LAVALINK_PORT=2333
LAVALINK_PASSWORD=<la stessa password>
MAIN_RADIO_LOCAL_FOLDER=/percorso/inediti      # come lo vede il bot
LAVALINK_LOCAL_ROOT=/audio/local               # come lo vede Lavalink (Docker)
```

Se il bot gira sullo stesso disco di Lavalink **senza Docker**, lascia
`LAVALINK_LOCAL_ROOT` vuota: si usa `MAIN_RADIO_LOCAL_FOLDER`.

## Come funziona il collegamento

- Ogni bot musicale (principale + 5 worker) apre **la sua** sessione verso
  ogni nodo (D10): un nodo e' legato a un solo utente bot.
- Il nodo locale e' sempre l'**ultimo** della scelta; i nodi pubblici
  (`LAVALINK_NODES` nel `.env`) vengono prima. Se la playlist della radio
  ha brani locali, la radio gira sul nodo locale.
- Ogni nodo si collega per conto suo, con 3 tentativi: un nodo morto non
  ferma gli altri. Se avvii Lavalink DOPO il bot, riavvia il bot.

## Sicurezza

- Il compose lega la porta a `127.0.0.1`: non esporla su Internet.
- `sources.local: true` fa leggere a chi ha la password qualunque file
  visibile al container: per questo vede **solo** `/audio/local`, in sola
  lettura. Non montare altro.
- Nessun segreto nei file di questa cartella (solo segnaposto).

## Controlli dopo l'avvio

```bash
curl -s -H "Authorization: $LAVALINK_PASSWORD" http://127.0.0.1:2333/v4/info | head -c 600
```

Controlla `version.semver` (>= 4.2.0) e `sourceManagers` (`youtube`,
`spotify`, `local`...). Poi: `/music play` con un titolo; `/owner radio
add-local` con un file della cartella. Le prove sul serio sono in
`revisione/03-verifica/VERIFICA_LIVE.md`.

Altro: `docs/music-lavalink.md` (documentazione ufficiale, nodi pubblici).
