"""
core/phishing_logic.py
======================
Confronto dei domini con la lista.
Funzioni coperte: SPEC §23 (NF-31)

STATO: scheletro. Il codice non è ancora scritto (issue #102).
"""

# ----------------------------------------------------------------------
# NOTA PER CHI SCRIVE QUESTO FILE — issue #102, fase F13
# Funzione: NF-31, Blocco dei link di phishing.
#
# Cosa deve fare la funzione: Il bot riconosce i link truffa più comuni
#   (finti regali Nitro, finti login) e li cancella.
# Questo file: Confronto dei domini con la lista.
# Comandi previsti: /security automod phishing.
# File collegati: core/phishing_list_fetcher.py.
# File esistenti da toccare: cogs/automod/automod.py.
# Test da scrivere per primi: tests/test_phishing_logic.py.
# Limiti da rispettare: Lista aggiornata da una fonte esterna: cache e
#   condizioni d'uso scritte in LIMITI.md.
# Da chi prendere spunto: Captcha.bot, Wick.
# Dipende da: message_content.
#
# Prima di iniziare: lista di controllo di
#   revisione/01-analisi/LIMITI.md (Parte 4); ogni impostazione passa da
#   un solo punto del codice, usato anche dal pannello web (decisione
#   D16); prima il test che fallisce, poi il codice.
# Dettaglio: revisione/02-piano/NUOVE_FUNZIONI.md e il catalogo in
#   revisione/01-analisi/catalogo/.
# ----------------------------------------------------------------------
