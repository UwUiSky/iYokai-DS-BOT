"""
core/nsfw_filter_logic.py
=========================
I due filtri: lista permessa e lista vietata.
Funzioni coperte: SPEC §16.10 (NF-23)

STATO: scheletro. Il codice non è ancora scritto (issue #94).
"""

# ----------------------------------------------------------------------
# NOTA PER CHI SCRIVE QUESTO FILE — issue #94, fase F11
# Funzione: NF-23, Istanza NSFW.
#
# Cosa deve fare la funzione: Un bot a parte (stesso codice, token
#   NSFW_TOKEN). Funziona solo nei canali segnati NSFW. Ricerca e
#   pubblicazione automatica, con due filtri obbligatori: lista permessa
#   scelta dal server e lista vietata fissa nel codice.
# Questo file: I due filtri: lista permessa e lista vietata.
# Comandi previsti: Comandi propri dell'istanza NSFW (non contano nei
#   100 del bot principale).
# File collegati: core/nsfw_bot.py, cogs/nsfw/__init__.py,
#   cogs/nsfw/ricerca.py, core/nsfw_autopost_worker.py,
#   core/repositories/nsfw_repo.py.
# Test da scrivere per primi: tests/test_nsfw_filter_logic.py,
#   tests/test_nsfw_canale.py.
# Migrazione: core/migrations/NNNN_nsfw.sql. (prossimo numero libero in
#   core/migrations/).
# Limiti da rispettare: Controllo del canale NSFW a ogni invio; registro
#   con hash di ogni immagine; contenuti vietati dalla legge bloccati
#   sempre.
# Da chi prendere spunto: Lawliet.
# Dipende da: NF-05, NF-06. Verifica dell'identità sul pannello (NF-20)
#   per l'invito.
#
# Prima di iniziare: lista di controllo di
#   revisione/01-analisi/LIMITI.md (Parte 4); ogni impostazione passa da
#   un solo punto del codice, usato anche dal pannello web (decisione
#   D16); prima il test che fallisce, poi il codice.
# Dettaglio: revisione/02-piano/NUOVE_FUNZIONI.md e il catalogo in
#   revisione/01-analisi/catalogo/.
# ----------------------------------------------------------------------
