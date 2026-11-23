# Memoria di dev-musica

## Aggiornata
23/11/2026 · ramo `feat/r7mus` · migrazione 0731 (giro r7mus, issue #126)

## In corso
- Giro r7mus: previste 3 voci (MUS-018, MUS-015, MUS-017; D111, D115). Fatta: MUS-018 (`cogs/music/cartella.py`,
  `core/music_cartella_logic.py`, `core/music_anteprime_logic.py`, tabelle 0731). Prossimo: vedi ultimo commit.
  Smoke da fare dall'orchestratore (invarianti albero, i18n, traduttore); prove live in VERIFICA_LIVE «r7mus».
- Giro r6mus FATTO (non unito): MUS-013, 022-026, 028, 033, 034, 046, 051, 052, 053, 061. `/owner` pesa ~7.4k con `cartella`: niente altri comandi owner senza controllare.

## Fatto
- r7mus: MUS-015 paese delle ricerche (D115): `music_paese_logic`, `/owner radio paese`, `/admin-musica impostazioni paese:`; filtro solo se la fonte dice i paesi.
- r7mus: MUS-018 cartella dell'owner (D115): scansione ogni 5 min, `/owner radio cartella`, `/music coda anteprime` (nel gruppo `coda`: `playlist` e' a 18 figli).
- r6/r10: 8.16 defer, sordo, allegato, canale richieste, playlist, suoni, nonstop, ALR-030..036, MUS-054/062/064.
- F2 (#64, #47+#48, #45, #126 parti 1-2), F7 3b (#76): nodi per bot, radio, deploy Lavalink, catalogo MUS, impostazioni.
- r6: `2d0b176` defer prima di Lavalink, bot sordo, allegato a play; `7ee6e39` canale richieste
  (`request_channel.py`, view persistente, aggiornamento max 1 ogni 5 s), playlist salva/carica/elenco/
  elimina/esporta/importa (tetti 25 x 200, file 256 KB), `/music suono` (soundboard; bot libero entra ed esce).
- Migrazioni: 0170 `music_request_channels`, 0171 `music_playlists`. Cacciatore r6: tracce decodificate filtrate, import robusto, pausa 3 s per utente, uscita del bot dei suoni col lock (`6b8faaf`, `b4a5cd1`, `3d93028`).

## Cose imparate
- r7mus: un brano `local` suona solo su un player del nodo locale; i dati mostrati agli utenti passano da `dati_traccia_pulita` (niente uri/percorso/copertina); `brano_da_traccia` rifiuta `source == local`.
- r7mus: `.env`/locales: `locales/*/testi.json` = indent 2 + a capo; `en-US/comandi.json` = indent 1 + a capo (scrivere con json.dumps, mai a mano).
- r6mus: `/music` ha 22 figli (tetto 25): comandi nuovi solo in sotto-gruppi (`coda`, `brano`). Il `remove-track` esistente e' della radio.
- r6mus: in un file di test non importare funzioni che iniziano per `test` (pytest le raccoglie): usare un alias di modulo.
- r6mus: nuove chiavi di impostazione = `music_settings_logic` + `config_history.py` (tipo) + `config_impostazioni.py` + `test_config_import_validation.py`.
- r6mus: `comandi.json` en-US ha formato non standard (1 spazio, poi 2): scriverlo con lo script che rifa' lo stesso formato, mai `json.dump(indent=2)`.
- r6mus: LRCLIB `/api/get` da' 404 se non trova (safe_get = None): solo `/api/search` (200 anche vuota) dice se il servizio c'e'.
- B3: i comandi che tolgono brani usano `_togli_dalla_coda` (clear + put senza await); l'ordine equo/mescola fisso passa da `_aggiungi_in_fondo`.
- Nei test dei comandi con permessi l'utente deve essere un `discord.Member` (`_controlli_base`): sottoclasse con `guild_permissions`.
- Opzioni dei comandi di gruppo: i test leggono `callback.__discord_app_commands_param_choices__` (il Command vero nasce dopo).
- Link Deezer: mai a Lavalink (niente `url_e_sicuro`): metadati da API, poi `cerca_testo` su altre fonti; un album diventa `wavelink.Playlist` da `raw_data`.
- Fonti (D73): tutto passa da `core/music_sources.py`; chiavi solo presenti sì/no (`chiavi_presenti`), `ripulisci()` per ogni testo d'errore; mai valori in log/messaggi.
- Un errore wavelink con `severity == "common"` (video tolto) NON è un guasto della fonte: non conta per la pausa. Risultato vuoto neppure.
- Il gate `fonte_usabile` consuma la «prova» dopo la pausa: chiamarlo una volta sola per ricerca (sta in `_cerca_su`).
- `deploy/lavalink/application.yml` è generato (`scripts/genera_lavalink_yml.py`); un test lo confronta col generato senza chiavi: rigenerare dopo ogni modifica.
- Il bot legge le chiavi dall'env solo per sapere se ci sono: senza `SPOTIFY_*` nell'.env del bot i link Spotify sono rifiutati anche se i nodi pubblici hanno LavaSrc.
- Pausa/filtri degli avvisi: `motivo_silenzio` in `alert_options_logic`; se zittito lo stato NON avanza (riprova al giro dopo), tranne i feed RSS che avanzano in silenzio.
- Player 24/7: `is_nonstop`/`is_radio` + `inactive_channel_tokens=None`; il default wavelink e' 3 (`CANALE_VUOTO_BRANI_DEFAULT`).
- Autocomplete nei sotto-gruppi: `@app_commands.autocomplete(nome=_metodo)` con il metodo del cog.
- Un bot assordato (self_deaf) NON manda suoni della soundboard: entrare con `sordo=False` o togliere
  la sordità prima di `send_sound`.
- Playlist salvate: decodifica in una richiesta sola `POST v4/decodetracks`; l'`encoded` decide cosa
  suona Lavalink (sorgente e identificatore), non il campo `uri` del file: va controllato DOPO la decodifica.
- Eventi wavelink dei worker arrivano al worker: ascoltarli con `worker.add_listener` (e toglierli in cog_unload).
- Mai `Playable.search` su testo utente: testo -> `Pool.fetch_tracks("ytmsearch:...")`; `local:` solo radio.
- D10: un nodo per bot (`<base>@<chiave>`); mai `Pool.get_node()`, usare `MusicNodeManager.node_for`.
- Nodo morto con retries finiti: `Pool.connect` non solleva; controllare `node.status`, `close(eject=True)`.
- Il player nasce sul nodo che ha dato i risultati: cerca, poi entra.
- Sessioni per (guild, canale); ogni azione su un player passa da `MusicCog._lock_canale`.
- Radio: `player.is_radio=True` + `inactive_channel_tokens=None`.
- Le View vanno in `core/` (ogni file di cogs/ e' un'estensione), salvo view legate al cog con add_view in setup.

## Aperto
- r5mus: il messaggio player del canale richieste non e' zittito durante «indovina la canzone» (provare live); i brani locali dell'owner sono esclusi dal gioco.
- r5mus: server radio-browser (de1/de2/fi1) e condizioni d'uso da verificare live (LIM-59).
- Domanda all'owner (MUS-027): pulizia AUTOMATICA all'uscita di un utente dal canale? Ora c'e' solo `/music coda pulisci` a mano.
- `mescola_fisso` si perde a un riavvio (solo in memoria, come da disegno).
- B2: l'API pubblica Deezer non e' stata letta nelle condizioni d'uso (dubbio D2 dell'owner); `_scarica_json` e' l'unico punto di rete.
- Prove live in VERIFICA_LIVE.md (Musica F2 e r6) da eseguire.
