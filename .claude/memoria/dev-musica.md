# Memoria di dev-musica

## Aggiornata
12/10/2026 · ramo `feat/r3-mus` (copia /home/claude/wt/mus) · base `c23a815` · DB iyokai_wmus · migrazioni da 0060

## In corso
- Previsione giro F2: 5 voci. Fatte: #64, #47+#48, #45, #126 parti 1 e 2. Prossimo: #90 (NF-19, canale
  richieste: migrazioni 0062/0063, `request_channel.py`, `music_request_logic/repo`, `music_playlist_repo`,
  view persistente) se resta spazio; poi #106 (`/fun suono`, serve un worker libero).
- /music ha 18 figli (limite 25): lasciare spazio a `playlist` (NF-19).

## Fatto
- F7 3b (#76): `/music` sotto-gruppi, `/owner radio` (`6d8894f`).
- F2 #64: 8.1-8.8, 8.10-8.15, 8.17, 8.18 (commit "Musica F2: un nodo per bot"). 8.16 e' di F1.
  Nuovi: `core/music_nodes.py` (gestore nodi), `core/music_radio_view.py`, migrazione 0060.
- F2 #47+#48: `deploy/lavalink/` (compose, application.yml segnaposto, README), `docs/music-lavalink.md`,
  `scripts/check_lavalink_nodes.py` (+ test).

- #45: avvio automatico radio, mkdir, traversal, avviso nodo locale mancante: gia' in F2 #64/#47.
- #126 parte 1: MUS-020 join, 021 play in-cima, 027 remove assenti, 029 skipto, 030 remove intervallo/utente,
  031 previous, 032 history, 035 queue cerca, 036 quote per utente, 039 shuffle solo-miei.
  Nuovo `core/music_queue_logic.py`; richiedente in `track.extras.requester_id`.

- #126 parte 2: MUS-044 durata massima, 047 volume massimo, 055 restare a coda finita, 059 canale permesso,
  066 riepilogo. `cogs/music/settings.py` (`/admin musica impostazioni|riepilogo`), `core/music_settings_logic.py`
  (impostazioni in guild_config.settings, nessuna tabella nuova). COMMAND_LIST.md rigenerato.

## Cose imparate
- D10: nodo per bot e per server Lavalink; Pool.nodes e' una mappa per identificatore: `<base>@<chiave>`
  (`main`, `w1`..`w5`). Pool.get_node() sceglie tra TUTTI i bot: mai usarlo, usare `MusicNodeManager.node_for`.
- wavelink: con `retries` finito e nodo morto `Pool.connect` NON solleva: il nodo resta DISCONNECTED nel Pool.
  Controllare `node.status` e fare `close(eject=True)`.
- `Playable.search` mette `ytmsearch:` a tutto cio' che non e' URL http (BUG-10): `spotify:` e `local:` vanno
  con `Pool.fetch_tracks`. `local:` solo dalla radio, mai da una ricerca utente (lettura file).
- Il player nasce sul nodo che ha dato i risultati (plugin LavaSrc/YouTube solo su certi nodi): cerca, poi entra.
- Sessioni per (guild, canale): PK doppia; ogni comando cerca la sessione nel canale dell'utente (cosi' 8.7 e' gratis).
- Il worker e' AutoShardedBot: nei test chiamare `await bot._async_setup_hook()` prima di `close()`.
- Radio: `player.is_radio=True` (esente da memory_guard e handle_inactive_player) + `inactive_channel_tokens=None`.
- Una View in `cogs/` non va bene (ogni file di cogs/ e' un'estensione con setup): le view stanno in `core/`.
- Config nuova: `LAVALINK_LOCAL_ROOT` (percorso visto dal nodo; Docker = punto di montaggio).

## Aperto
- 8.16 (defer nei comandi musicali) e' di F1; 8.19 = NF-19 (#90).
- Prove live scritte in VERIFICA_LIVE.md (sezione «Musica F2»); da eseguire: audio dai 5 worker, due canali/stesso server, radio in canale vuoto,
  ingresso del principale in vocale, brano locale, nodo 4.1 scartato, canale palco/pieno.
- `LAVALINK_NODES` e' vuoto di default: senza nodi pubblici in .env resta solo il locale.
