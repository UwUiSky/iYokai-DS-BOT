"""
core/rank_card_image.py
=======================
Disegna la rank card.
Funzioni coperte: SPEC §22 (NF-12)

STATO: scheletro. Il codice non è ancora scritto (issue #83).
"""

# ----------------------------------------------------------------------
# NOTA PER CHI SCRIVE QUESTO FILE — issue #83, fase F9
# Funzione: NF-12, Rank card.
#
# Cosa deve fare la funzione: rank mostra un'immagine con avatar,
#   livello, barra dell'XP e posizione in classifica. Colore e sfondo a
#   scelta.
# Questo file: Disegna la rank card.
# Comandi previsti: /level rank.
# File esistenti da toccare: cogs/leveling/leveling.py.
# Test da scrivere per primi: tests/test_rank_card_image.py.
# Limiti da rispettare: defer() prima di disegnare; regole di
#   core/safe_image.py.
# Da chi prendere spunto: MEE6 (colori gratis, sfondo premium), Arcane,
#   Carl-bot.
# Dipende da: Nessuna.
#
# Prima di iniziare: lista di controllo di
#   revisione/01-analisi/LIMITI.md (Parte 4); ogni impostazione passa da
#   un solo punto del codice, usato anche dal pannello web (decisione
#   D16); prima il test che fallisce, poi il codice.
# Dettaglio: revisione/02-piano/NUOVE_FUNZIONI.md e il catalogo in
#   revisione/01-analisi/catalogo/.
# ----------------------------------------------------------------------
