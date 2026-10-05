"""
core/coin_games_logic.py
========================
Regole dei giochi.
Funzioni coperte: SPEC §23 (NF-40)

STATO: scheletro. Il codice non è ancora scritto (issue #111).
"""

# ----------------------------------------------------------------------
# NOTA PER CHI SCRIVE QUESTO FILE — issue #111, fase F13
# Funzione: NF-40, Profili, collezioni e giochi con le monete.
#
# Cosa deve fare la funzione: Profilo personale con sfondo e badge.
#   Oggetti da collezionare. Giochi semplici con le monete (senza soldi
#   veri). Include un misuratore casuale a tema libero, alternativa
#   neutra a SPEC §16.6, e il gioco del conteggio in un canale.
# Questo file: Regole dei giochi.
# Comandi previsti: /level profilo, /fun gioca …, /fun misura.
# File collegati: cogs/fun/coin_games.py, cogs/leveling/profiles.py,
#   core/repositories/profile_repo.py.
# Test da scrivere per primi: tests/test_coin_games_logic.py,
#   tests/test_profiles.py.
# Migrazione: core/migrations/NNNN_profiles.sql. (prossimo numero libero
#   in core/migrations/).
# Limiti da rispettare: Discord vieta di monetizzare il gioco d'azzardo:
#   le monete di questi giochi non si comprano mai con soldi veri.
# Da chi prendere spunto: Tatsu, Dank Memer, UnbelievaBoat.
# Dipende da: BUG-14 sistemato (monete senza doppi accrediti).
#
# Prima di iniziare: lista di controllo di
#   revisione/01-analisi/LIMITI.md (Parte 4); ogni impostazione passa da
#   un solo punto del codice, usato anche dal pannello web (decisione
#   D16); prima il test che fallisce, poi il codice.
# Dettaglio: revisione/02-piano/NUOVE_FUNZIONI.md e il catalogo in
#   revisione/01-analisi/catalogo/.
# ----------------------------------------------------------------------
