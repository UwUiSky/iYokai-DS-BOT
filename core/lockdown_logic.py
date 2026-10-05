"""
core/lockdown_logic.py
======================
Cosa bloccare e come ripristinare.
Funzioni coperte: SPEC §23 (NF-29)

STATO: scheletro. Il codice non è ancora scritto (issue #100).
"""

# ----------------------------------------------------------------------
# NOTA PER CHI SCRIVE QUESTO FILE — issue #100, fase F13
# Funzione: NF-29, Blocco totale del server e "panic mode".
#
# Cosa deve fare la funzione: Un comando blocca tutti i canali, gli
#   inviti e gli ingressi, e un altro riapre tutto com'era. Durante un
#   attacco riconosciuto può scattare da solo.
# Questo file: Cosa bloccare e come ripristinare.
# Comandi previsti: /mod blocco attiva|togli, /security panico ….
# File collegati: cogs/security/lockdown.py,
#   core/repositories/lockdown_repo.py.
# Test da scrivere per primi: tests/test_lockdown.py.
# Migrazione: core/migrations/NNNN_lockdown.sql. (prossimo numero libero
#   in core/migrations/).
# Limiti da rispettare: 500 canali: lavoro lungo, defer() e riepilogo
#   nel canale; stato salvato per poter riaprire.
# Da chi prendere spunto: Wick (lockdown e panic mode).
# Dipende da: BUG-11 e BUG-12 sistemati.
#
# Prima di iniziare: lista di controllo di
#   revisione/01-analisi/LIMITI.md (Parte 4); ogni impostazione passa da
#   un solo punto del codice, usato anche dal pannello web (decisione
#   D16); prima il test che fallisce, poi il codice.
# Dettaglio: revisione/02-piano/NUOVE_FUNZIONI.md e il catalogo in
#   revisione/01-analisi/catalogo/.
# ----------------------------------------------------------------------
