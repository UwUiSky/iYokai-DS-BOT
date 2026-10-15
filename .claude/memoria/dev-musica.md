# Memoria di dev-musica

## Aggiornata
15/10/2026 · ramo `feat/r6mus` (copia /home/claude/wt/r6mus) · migrazioni 0170–0171

## In corso
- Giro r6 CHIUSO (8.16 defer, MUS-056 sordo, MUS-009 allegato, NF-19 canale richieste + playlist, NF-35 suoni).
  Prossimo: prove live in VERIFICA_LIVE.md; nessuna voce aperta in codice.

## Fatto
- F2 (#64, #47+#48, #45, #126 parti 1-2), F7 3b (#76): nodi per bot, radio, deploy Lavalink, catalogo MUS, impostazioni.
- r6: `2d0b176` defer prima di Lavalink, bot sordo, allegato a play; `7ee6e39` canale richieste
  (`request_channel.py`, view persistente, aggiornamento max 1 ogni 5 s), playlist salva/carica/elenco/
  elimina/esporta/importa (tetti 25 x 200, file 256 KB), `/music suono` (soundboard; bot libero entra ed esce).
- Migrazioni: 0170 `music_request_channels`, 0171 `music_playlists`.
- Cacciatore r6 (15/10): tracce decodificate filtrate (no `local`, URL solo pubblici, `riferimenti_traccia`)
  `6b8faaf`; import robusto (annidato, Infinity, durata limitata); pausa segnata prima dell'await nel
  player; pausa 3 s per utente nel canale richieste `b4a5cd1`; uscita del bot dei suoni col lock del
  canale e spostata da un nuovo suono `3d93028`.

## Cose imparate
- Autocomplete nei sotto-gruppi: `@app_commands.autocomplete(nome=_metodo)` con il metodo del cog.
- Un bot assordato (self_deaf) NON manda suoni della soundboard: entrare con `sordo=False` o togliere
  la sordità prima di `send_sound`.
- Playlist salvate: decodifica in una richiesta sola `POST v4/decodetracks`; l'`encoded` decide cosa
  suona Lavalink (sorgente e identificatore), non il campo `uri` del file: va controllato DOPO la decodifica.
- Eventi wavelink dei worker arrivano al worker: ascoltarli con `worker.add_listener` (e toglierli in cog_unload).
- `/admin` e' a ~6577 caratteri di definizione (tetto Discord 8000): poco spazio per nuovi figli.
- `Pool.connect` torna con il nodo CONNECTING; CONNECTED arriva con `ready`.
- Mai `Playable.search` su testo utente: testo -> `Pool.fetch_tracks("ytmsearch:...")`; `local:` solo radio.
- D10: un nodo per bot (`<base>@<chiave>`); mai `Pool.get_node()`, usare `MusicNodeManager.node_for`.
- Nodo morto con retries finiti: `Pool.connect` non solleva; controllare `node.status`, `close(eject=True)`.
- Il player nasce sul nodo che ha dato i risultati: cerca, poi entra.
- Sessioni per (guild, canale); ogni azione su un player passa da `MusicCog._lock_canale`.
- Worker AutoShardedBot: nei test `await bot._async_setup_hook()` prima di `close()`.
- Radio: `player.is_radio=True` + `inactive_channel_tokens=None`.
- Le View vanno in `core/` (ogni file di cogs/ e' un'estensione), salvo view legate al cog con add_view in setup.
- Pause "una ogni N secondi": segnare prima del primo await, se no due chiamate insieme passano.

## Aperto
- `_torna_sordo`: due suoni entro 6 s, il primo riassorda il bot durante il secondo (bassa).
- URL pubblici verificati da noi, risolti di nuovo da Lavalink: DNS rebinding resta possibile.
- Prove live in VERIFICA_LIVE.md (Musica F2 e r6) da eseguire.
- `LAVALINK_NODES` vuoto di default: senza nodi pubblici resta solo il locale.
