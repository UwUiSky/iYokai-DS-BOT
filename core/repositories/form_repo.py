"""
core/repositories/form_repo.py
==============================
Moduli e risposte.
Funzioni coperte: SPEC §23 (NF-34)

STATO: scheletro. Il codice non è ancora scritto (issue #105).
"""

# ----------------------------------------------------------------------
# NOTA PER CHI SCRIVE QUESTO FILE — issue #105, fase F13
# Funzione: NF-34, Moduli e candidature.
#
# Cosa deve fare la funzione: L'admin crea un modulo (candidatura staff,
#   ingresso in un clan). Le risposte arrivano in un canale con bottoni
#   accetta e rifiuta.
# Questo file: Moduli e risposte.
# Comandi previsti: /admin moduli crea|elimina|elenco, /utility modulo.
# File collegati: cogs/utility/forms.py, core/form_logic.py.
# Test da scrivere per primi: tests/test_forms.py.
# Migrazione: core/migrations/NNNN_forms.sql. (prossimo numero libero in
#   core/migrations/).
# Limiti da rispettare: 5 campi per modulo; etichetta 45; risposte in
#   campi da 1024.
# Da chi prendere spunto: Dyno (form builder), Circle.
# Dipende da: NF-13 (stessa logica dei moduli).
#
# Prima di iniziare: lista di controllo di
#   revisione/01-analisi/LIMITI.md (Parte 4); ogni impostazione passa da
#   un solo punto del codice, usato anche dal pannello web (decisione
#   D16); prima il test che fallisce, poi il codice.
# Dettaglio: revisione/02-piano/NUOVE_FUNZIONI.md e il catalogo in
#   revisione/01-analisi/catalogo/.
# ----------------------------------------------------------------------
