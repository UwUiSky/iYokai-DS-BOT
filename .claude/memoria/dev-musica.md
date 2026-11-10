# Memoria di dev-musica

## Aggiornata
10/11/2026 · ramo `feat/r2mus` (/home/claude/wt/r2mus) · nessuna migrazione (B1 e B2 senza tabelle; B3 parte da 0620)

## In corso
- #126 B1 e B2 FATTI (B2: opzione `fonte`, `music_default_search` in SETTINGS_SCHEMA+SCHEDE+`/admin-musica impostazioni ricerca-predefinita`,
  Deezer solo metadati ISRC poi titolo, yml con tidal/yandexmusic, residui B1 in locales). Prossimo: B3 coda (migr. 0620) nel sotto-gruppo
  `/music coda` (`/music` <=18 figli, peso <6.800): MUS-030, 035, 027, 037, 038. Aperte B2: `music_sources_off`, `music_country`, solo-audio (016),
  avviso scadenza token Apple a 14 giorni, scelte di `fonte` fisse (6) non filtrate per owner.
- Giro r10 (musica + alert, agente r10musa): SPEC 9.x e 10.x tutte `[x]`; fatti nonstop 24/7, ALR-030/031/032/033/036, MUS-054/062/064.
  Prossimo: ALR-037/038/040 (sposta, ferma tutti, controllo a mano) servono sotto-comandi in /moduli alert (chiedere guardiano-limiti); MUS-061 stato del bot, MUS-053.
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
- Opzioni dei comandi di gruppo: i test leggono `callback.__discord_app_commands_param_choices__` (il Command vero nasce dopo).
- Link Deezer: mai a Lavalink (niente `url_e_sicuro`): metadati da API, poi `cerca_testo` su altre fonti; un album diventa `wavelink.Playlist` da `raw_data`.
- Fonti (D73): tutto passa da `core/music_sources.py`; chiavi solo presenti sì/no (`chiavi_presenti`), `ripulisci()` per ogni testo d'errore; mai valori in log/messaggi.
- Un errore wavelink con `severity == "common"` (video tolto) NON è un guasto della fonte: non conta per la pausa. Risultato vuoto neppure.
- Il gate `fonte_usabile` consuma la «prova» dopo la pausa: chiamarlo una volta sola per ricerca (sta in `_cerca_su`).
- `deploy/lavalink/application.yml` è generato (`scripts/genera_lavalink_yml.py`); un test lo confronta col generato senza chiavi: rigenerare dopo ogni modifica.
- Il bot legge le chiavi dall'env solo per sapere se ci sono: senza `SPOTIFY_*` nell'.env del bot i link Spotify sono rifiutati anche se i nodi pubblici hanno LavaSrc.
- Le note «Stato 04/10» della SPEC erano superate: prima di toccare una voce `[~]` controllare codice e REGISTRO.
- Pausa/filtri degli avvisi: `motivo_silenzio` in `alert_options_logic`; se zittito lo stato NON avanza (riprova al giro dopo), tranne i feed RSS che avanzano in silenzio.
- Player 24/7: `is_nonstop`/`is_radio` + `inactive_channel_tokens=None`; il default wavelink e' 3 (`CANALE_VUOTO_BRANI_DEFAULT`).
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
- B2: l'API pubblica Deezer non e' stata letta nelle condizioni d'uso (dubbio D2 dell'owner); `_scarica_json` e' l'unico punto di rete.
- `_torna_sordo`: due suoni entro 6 s, il primo riassorda il bot durante il secondo (bassa).
- URL pubblici verificati da noi, risolti di nuovo da Lavalink: DNS rebinding resta possibile.
- Prove live in VERIFICA_LIVE.md (Musica F2 e r6) da eseguire.
- `LAVALINK_NODES` vuoto di default: senza nodi pubblici resta solo il locale.
