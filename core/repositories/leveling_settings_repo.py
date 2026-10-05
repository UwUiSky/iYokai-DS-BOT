"""
core/repositories/leveling_settings_repo.py
===========================================
Impostazioni dei livelli per server.
Funzioni coperte: SPEC §22 (NF-15)

STATO: scheletro. Il codice non è ancora scritto (issue #86).
"""

# ----------------------------------------------------------------------
# NOTA PER CHI SCRIVE QUESTO FILE — issue #86, fase F9
# Funzione: NF-15, Impostazioni dei livelli.
#
# Cosa deve fare la funzione: Canali e ruoli senza XP. Moltiplicatori
#   per canale e per ruolo. Scelta di dove annunciare il level-up
#   (spento, canale corrente, DM, canale scelto). Premi "accumula" o
#   "togli i precedenti". XP e monete configurabili per server.
# Questo file: Impostazioni dei livelli per server.
# Comandi previsti: /admin economia livelli ….
# File esistenti da toccare: cogs/leveling/leveling.py,
#   core/leveling_logic.py.
# Test da scrivere per primi: tests/test_leveling_settings.py.
# Migrazione: core/migrations/NNNN_leveling_settings.sql. (prossimo
#   numero libero in core/migrations/).
# Limiti da rispettare: 25 scelte per opzione; valori con minimo e
#   massimo.
# Da chi prendere spunto: MEE6, ProBot, Maki.
# Dipende da: Nessuna.
#
# Prima di iniziare: lista di controllo di
#   revisione/01-analisi/LIMITI.md (Parte 4); ogni impostazione passa da
#   un solo punto del codice, usato anche dal pannello web (decisione
#   D16); prima il test che fallisce, poi il codice.
# Dettaglio: revisione/02-piano/NUOVE_FUNZIONI.md e il catalogo in
#   revisione/01-analisi/catalogo/.
# ----------------------------------------------------------------------
