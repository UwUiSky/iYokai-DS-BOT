"""
core/ban_appeal_logic.py
========================
Regole comuni agli appelli (spam-trap e ban manuali).
Funzioni coperte: SPEC §23 (NF-30)

STATO: scheletro. Il codice non è ancora scritto (issue #101).
"""

# ----------------------------------------------------------------------
# NOTA PER CHI SCRIVE QUESTO FILE — issue #101, fase F13
# Funzione: NF-30, Appello per i ban normali.
#
# Cosa deve fare la funzione: Chi viene bannato a mano può chiedere una
#   revisione in DM, come già succede per lo spam-trap.
# Questo file: Regole comuni agli appelli (spam-trap e ban manuali).
# Comandi previsti: /admin config appelli.
# File collegati: cogs/moderation/ban_appeal.py.
# File esistenti da toccare: cogs/security/spam_trap.py.
# Test da scrivere per primi: tests/test_ban_appeal.py.
# Limiti da rispettare: Un appello ogni 24 ore; View persistente; solo
#   chi ha "Bannare membri" decide.
# Da chi prendere spunto: Circle ("Ban Appeals").
# Dipende da: LC-5 sistemato (bottoni di appello persistenti).
#
# Prima di iniziare: lista di controllo di
#   revisione/01-analisi/LIMITI.md (Parte 4); ogni impostazione passa da
#   un solo punto del codice, usato anche dal pannello web (decisione
#   D16); prima il test che fallisce, poi il codice.
# Dettaglio: revisione/02-piano/NUOVE_FUNZIONI.md e il catalogo in
#   revisione/01-analisi/catalogo/.
# ----------------------------------------------------------------------
