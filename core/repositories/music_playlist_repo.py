"""
core/repositories/music_playlist_repo.py
========================================
Playlist salvate degli utenti.
Funzioni coperte: SPEC §23 (NF-19)

STATO: scheletro. Il codice non è ancora scritto (issue #90).
"""

# ----------------------------------------------------------------------
# NOTA PER CHI SCRIVE QUESTO FILE — issue #90, fase F9
# Funzione: NF-19, Canale richieste musicali con player, playlist
#   salvate.
#
# Cosa deve fare la funzione: Un canale dedicato con un messaggio
#   "player" sempre aggiornato e bottoni (pausa, salta, stop, mescola,
#   ripeti). Chi scrive un titolo nel canale lo mette in coda. Ogni
#   utente può salvare playlist. Nessun ruolo DJ e nessun voto (scelta
#   dell'owner).
# Questo file: Playlist salvate degli utenti.
# Comandi previsti: /admin musica canale-richieste, /music playlist
#   salva|carica|elenco|elimina.
# File collegati: cogs/music/request_channel.py,
#   core/music_request_logic.py,
#   core/repositories/music_request_repo.py.
# File esistenti da toccare: cogs/music/player.py.
# Test da scrivere per primi: tests/test_music_request_channel.py,
#   tests/test_music_playlist.py.
# Migrazione: core/migrations/NNNN_music_request.sql,
#   core/migrations/NNNN_music_playlist.sql. (prossimo numero libero in
#   core/migrations/).
# Limiti da rispettare: View persistente; 5 bottoni per riga; titolo 256
#   (LIM-21); aggiornamento del messaggio non più di una volta ogni
#   pochi secondi.
# Da chi prendere spunto: Hydra (storico), Jockie (raccolte).
# Dipende da: F2 finita (D10) e provata live. message_content.
#
# Prima di iniziare: lista di controllo di
#   revisione/01-analisi/LIMITI.md (Parte 4); ogni impostazione passa da
#   un solo punto del codice, usato anche dal pannello web (decisione
#   D16); prima il test che fallisce, poi il codice.
# Dettaglio: revisione/02-piano/NUOVE_FUNZIONI.md e il catalogo in
#   revisione/01-analisi/catalogo/.
# ----------------------------------------------------------------------
