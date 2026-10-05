"""
core/ticket_form_logic.py
=========================
Domande del modulo e controllo delle risposte.
Funzioni coperte: SPEC §22 (NF-13)

STATO: scheletro. Il codice non è ancora scritto (issue #84).
"""

# ----------------------------------------------------------------------
# NOTA PER CHI SCRIVE QUESTO FILE — issue #84, fase F9
# Funzione: NF-13, Ticket: modulo, più pannelli, chiusura automatica,
#   voto.
#
# Cosa deve fare la funzione: Prima di aprire un ticket l'utente compila
#   un modulo (fino a 5 domande). Un messaggio può avere più pannelli.
#   Un ticket fermo si chiude da solo. Alla chiusura l'utente dà un
#   voto. Limite di ticket aperti per utente.
# Questo file: Domande del modulo e controllo delle risposte.
# Comandi previsti: /admin ticket modulo, /admin ticket pannello, /admin
#   ticket chiusura-auto.
# File collegati: core/repositories/ticket_form_repo.py,
#   core/ticket_autoclose_worker.py.
# File esistenti da toccare: cogs/tickets/tickets.py,
#   core/ticket_logic.py, core/repositories/ticket_repo.py.
# Test da scrivere per primi: tests/test_ticket_form.py,
#   tests/test_ticket_autoclose.py.
# Migrazione: core/migrations/NNNN_ticket_form.sql. (prossimo numero
#   libero in core/migrations/).
# Limiti da rispettare: 5 campi per modulo, etichetta 45; 25 opzioni per
#   menu (LIM-6); 5 bottoni per riga; chiusura tramite scheduler.
# Da chi prendere spunto: Ticket Tool (25 pannelli, 5 domande,
#   transcript), Tickets (chiusura automatica, voto a stelle).
# Dipende da: BUG-30 (fatto).
#
# Prima di iniziare: lista di controllo di
#   revisione/01-analisi/LIMITI.md (Parte 4); ogni impostazione passa da
#   un solo punto del codice, usato anche dal pannello web (decisione
#   D16); prima il test che fallisce, poi il codice.
# Dettaglio: revisione/02-piano/NUOVE_FUNZIONI.md e il catalogo in
#   revisione/01-analisi/catalogo/.
# ----------------------------------------------------------------------
