# Memoria di dev-musica

## Aggiornata
18/11/2026 · ramo `feat/r5mus` · migrazioni 0730-0739 (giro r5mus)

## In corso
- Giro r5mus (#126): MUS-010 FATTO (`core/music_radio_mondo.py`, `/music radio`), MUS-014 FATTO (0730, `/music genere`, `/owner radio genere`); MUS-065 FATTO (jukebox in `accoda`/`_con_jukebox`), MUS-019 FATTO (`cogs/music/indovina.py`, registro `in_gioco` per non rivelare titoli). Giro r5mus CHIUSO: restano le prove live (VERIFICA_LIVE r5mus). `/owner` pesa 6715 (avviso a 6800): niente altri comandi owner. D97 in DECISIONI.
- Giro r4mus FATTO (non unito): annunci/copertina, playlist (crea/aggiungi/togli/rinomina/da link/aggiorna/codice/server/collabora/preferiti), owner (`/owner radio nodi|stato|riconnetti|log|sorgente|blocca-parola`), riserva, «Oggi», coda salvata.
  Prossimo: MUS-010, 014, 019, 065 (vedi D85 «Restano»); eventi in `cogs/music/eventi.py`, owner in `cogs/music/owner.py`.
- #126 B1, B2, B3 FATTI (B3 «coda»: `/music coda cerca|salta|pulisci`, impostazione `music_queue_mode` normale/equa con
  `/admin-musica impostazioni coda:`, `/music shuffle resta:` con `player.mescola_fisso` in memoria). Aperte B2: `music_sources_off`,
  `music_country`, solo-audio (016), avviso scadenza token Apple a 14 giorni, scelte di `fonte` fisse (6) non filtrate per owner.
  Prossimo: prove live (VERIFICA_LIVE «Musica — coda»); resto del catalogo #126 non ancora fatto (guardare SPEC 9.x `[ ]`).

## Fatto
- r6/r10: 8.16 defer, sordo, allegato, canale richieste, playlist, suoni, nonstop, ALR-030..036, MUS-054/062/064.
- F2 (#64, #47+#48, #45, #126 parti 1-2), F7 3b (#76): nodi per bot, radio, deploy Lavalink, catalogo MUS, impostazioni.
- r6: `2d0b176` defer prima di Lavalink, bot sordo, allegato a play; `7ee6e39` canale richieste
  (`request_channel.py`, view persistente, aggiornamento max 1 ogni 5 s), playlist salva/carica/elenco/
  elimina/esporta/importa (tetti 25 x 200, file 256 KB), `/music suono` (soundboard; bot libero entra ed esce).
- Migrazioni: 0170 `music_request_channels`, 0171 `music_playlists`. Cacciatore r6: tracce decodificate filtrate, import robusto, pausa 3 s per utente, uscita del bot dei suoni col lock (`6b8faaf`, `b4a5cd1`, `3d93028`).

## Cose imparate
- B3: i comandi che tolgono brani usano `_togli_dalla_coda` (clear + put senza await); l'ordine equo/mescola fisso passa da `_aggiungi_in_fondo`.
- Nei test dei comandi con permessi l'utente deve essere un `discord.Member` (`_controlli_base`): sottoclasse con `guild_permissions`.
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
- r5mus: il messaggio player del canale richieste non e' zittito durante «indovina la canzone» (provare live); i brani locali dell'owner sono esclusi dal gioco.
- r5mus: server radio-browser (de1/de2/fi1) e condizioni d'uso da verificare live (LIM-59).
- r4mus: log Lavalink (`LAVALINK_LOG_FILE`) e annunci da provare live; la riserva parte da `track_end` (ordine con `_auto_play_event` non verificabile qui, attesa 0,5 s).
- Domanda all'owner (MUS-027): pulizia AUTOMATICA all'uscita di un utente dal canale? Ora c'e' solo `/music coda pulisci` a mano.
- `mescola_fisso` si perde a un riavvio (solo in memoria, come da disegno).
- B2: l'API pubblica Deezer non e' stata letta nelle condizioni d'uso (dubbio D2 dell'owner); `_scarica_json` e' l'unico punto di rete.
- `_torna_sordo`: due suoni entro 6 s, il primo riassorda il bot durante il secondo (bassa).
- URL pubblici verificati da noi, risolti di nuovo da Lavalink: DNS rebinding resta possibile.
- Prove live in VERIFICA_LIVE.md (Musica F2 e r6) da eseguire.
- `LAVALINK_NODES` vuoto di default: senza nodi pubblici resta solo il locale.
