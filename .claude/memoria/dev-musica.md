# Memoria di dev-musica

## Aggiornata
12/10/2026 · ramo `feat/r3-mus` (copia /home/claude/wt/mus) · base `c23a815` · DB iyokai_wmus · migrazioni da 0060

## In corso
- Previsione giro F2: 5 voci (#64, #47+#48, #45, #126 piccole, poi #90/#106 se resta spazio).
- Fatto #64 (tranne 8.16, 8.19) e #47+#48. Prossimo: #45 (resta: add-local con traversal gia' coperto;
  verificare cascade/documento) poi #126 piccole nello stesso codice (MUS-020, 021, 029, 031, 032,
  035, 053-057...). Sezioni di /music: contare i figli (max 25) prima di aggiungere comandi.

## Fatto
- F7 3b (#76): `/music` sotto-gruppi, `/owner radio` (`6d8894f`).
- F2 #64: 8.1-8.8, 8.10-8.15, 8.17, 8.18 (commit "Musica F2: un nodo per bot"). 8.16 e' di F1.
  Nuovi: `core/music_nodes.py` (gestore nodi), `core/music_radio_view.py`, migrazione 0060.
- F2 #47+#48: `deploy/lavalink/` (compose, application.yml segnaposto, README), `docs/music-lavalink.md`,
  `scripts/check_lavalink_nodes.py` (+ test).

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
- Prova live (VERIFICA_LIVE.md): audio dai 5 worker, due canali/stesso server, radio in canale vuoto,
  ingresso del principale in vocale, brano locale, nodo 4.1 scartato, canale palco/pieno.
- `LAVALINK_NODES` e' vuoto di default: senza nodi pubblici in .env resta solo il locale.
