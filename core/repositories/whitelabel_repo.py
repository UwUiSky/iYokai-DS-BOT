"""
core/repositories/whitelabel_repo.py
====================================
Token cifrati e stato.
Funzioni coperte: SPEC §23 (NF-38)

STATO: scheletro. Il codice non è ancora scritto (issue #109).
"""

# ----------------------------------------------------------------------
# NOTA PER CHI SCRIVE QUESTO FILE — issue #109, fase F13
# Funzione: NF-38, Bot con marchio proprio.
#
# Cosa deve fare la funzione: Un server premium usa il bot con nome e
#   avatar suoi.
# Questo file: Token cifrati e stato.
# Comandi previsti: /admin premium marchio.
# File collegati: core/whitelabel_bot.py.
# Test da scrivere per primi: tests/test_whitelabel_bot.py.
# Migrazione: core/migrations/NNNN_whitelabel.sql. (prossimo numero
#   libero in core/migrations/).
# Limiti da rispettare: Ogni bot in più è un'applicazione Discord con
#   token proprio, cifrato a riposo.
# Da chi prendere spunto: MEE6 (Bot Personalizer), Tickets (6,99
#   $/mese), Sapphire.
# Dipende da: NF-22.
#
# Prima di iniziare: lista di controllo di
#   revisione/01-analisi/LIMITI.md (Parte 4); ogni impostazione passa da
#   un solo punto del codice, usato anche dal pannello web (decisione
#   D16); prima il test che fallisce, poi il codice.
# Dettaglio: revisione/02-piano/NUOVE_FUNZIONI.md e il catalogo in
#   revisione/01-analisi/catalogo/.
# ----------------------------------------------------------------------
