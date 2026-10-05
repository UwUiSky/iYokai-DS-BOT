"""
core/autorole_logic.py
======================
Decide quali ruoli dare e quando.
Funzioni coperte: SPEC §22 (NF-07)

STATO: scheletro. Il codice non è ancora scritto (issue #78).
"""

# ----------------------------------------------------------------------
# NOTA PER CHI SCRIVE QUESTO FILE — issue #78, fase F9
# Funzione: NF-07, Ruolo automatico all'ingresso, ruoli ridati a chi
#   rientra, ruoli a tempo.
#
# Cosa deve fare la funzione: Chi entra riceve uno o più ruoli. Chi esce
#   e rientra entro 30 giorni riprende i ruoli che aveva. Un ruolo può
#   essere dato dopo un ritardo.
# Questo file: Decide quali ruoli dare e quando.
# Comandi previsti: /admin ruoli auto aggiungi|rimuovi|elenco, /admin
#   ruoli ricorda.
# File collegati: cogs/utility/autoroles.py,
#   core/repositories/autorole_repo.py.
# Test da scrivere per primi: tests/test_autoroles.py.
# Migrazione: core/migrations/NNNN_autoroles.sql. (prossimo numero
#   libero in core/migrations/).
# Limiti da rispettare: 250 ruoli; check_role_assignable alla
#   configurazione e all'assegnazione; niente ruoli ai bot; pausa
#   durante un raid.
# Da chi prendere spunto: Carl-bot (autorole, ruoli ridati entro 30
#   giorni, ruoli a tempo), Arcane.
# Dipende da: Nessuna. Va d'accordo con Verify: se la verifica è attiva,
#   il ruolo arriva dopo.
#
# Prima di iniziare: lista di controllo di
#   revisione/01-analisi/LIMITI.md (Parte 4); ogni impostazione passa da
#   un solo punto del codice, usato anche dal pannello web (decisione
#   D16); prima il test che fallisce, poi il codice.
# Dettaglio: revisione/02-piano/NUOVE_FUNZIONI.md e il catalogo in
#   revisione/01-analisi/catalogo/.
# ----------------------------------------------------------------------
