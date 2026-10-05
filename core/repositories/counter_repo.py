"""
core/repositories/counter_repo.py
=================================
Contatori configurati.
Funzioni coperte: SPEC §23 (NF-16)

STATO: scheletro. Il codice non è ancora scritto (issue #87).
"""

# ----------------------------------------------------------------------
# NOTA PER CHI SCRIVE QUESTO FILE — issue #87, fase F13
# Funzione: NF-16, Canali contatore.
#
# Cosa deve fare la funzione: Canali il cui nome mostra un numero:
#   membri, membri online, boost, obiettivo.
# Questo file: Contatori configurati.
# Comandi previsti: /admin contatori crea|elimina|elenco.
# File collegati: cogs/utility/counters.py, core/counter_logic.py,
#   core/counter_worker.py.
# Test da scrivere per primi: tests/test_counters.py.
# Migrazione: core/migrations/NNNN_counters.sql. (prossimo numero libero
#   in core/migrations/).
# Limiti da rispettare: Rinomina 2 ogni 10 minuti per canale:
#   aggiornamento al massimo ogni 10 minuti (LIM-3); tetto per server.
# Da chi prendere spunto: ServerStats, Arcane (3 gratis), Statbot.
# Dipende da: Nessuna.
#
# Prima di iniziare: lista di controllo di
#   revisione/01-analisi/LIMITI.md (Parte 4); ogni impostazione passa da
#   un solo punto del codice, usato anche dal pannello web (decisione
#   D16); prima il test che fallisce, poi il codice.
# Dettaglio: revisione/02-piano/NUOVE_FUNZIONI.md e il catalogo in
#   revisione/01-analisi/catalogo/.
# ----------------------------------------------------------------------
