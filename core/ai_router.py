"""
core/ai_router.py
=================
Sceglie il fornitore, passa al successivo se uno fallisce.
Funzioni coperte: SPEC §25 (NF-24)

STATO: scheletro. Il codice non è ancora scritto (issue #95).
"""

# ----------------------------------------------------------------------
# NOTA PER CHI SCRIVE QUESTO FILE — issue #95, fase F12
# Funzione: NF-24, Motore AI.
#
# Cosa deve fare la funzione: Un motore unico con più fornitori in
#   cascata e una risposta locale di riserva. Sopra ci stanno: aiuto sui
#   comandi (helpdesk), riassunti di canali e ticket, "lore" del server
#   (tono e ambientazione scelti dall'admin), generazione di immagini.
#   Con memoria delle risposte già date, filtri di sicurezza e tetto di
#   spesa.
# Questo file: Sceglie il fornitore, passa al successivo se uno
#   fallisce.
# Comandi previsti: /admin ai … (configurazione), /utility chiedi,
#   /utility riassumi, /fun immagina.
# File collegati: core/ai_cache_logic.py, core/ai_guardrail_logic.py,
#   core/ai_cost_logic.py, core/repositories/ai_repo.py,
#   cogs/ai/__init__.py, cogs/ai/helpdesk.py, cogs/ai/summaries.py,
#   cogs/ai/lore.py, cogs/ai/images.py.
# Test da scrivere per primi: tests/test_ai_router.py,
#   tests/test_ai_guardrail_logic.py, tests/test_ai_cost_logic.py.
# Migrazione: core/migrations/NNNN_ai.sql. (prossimo numero libero in
#   core/migrations/).
# Limiti da rispettare: Vietato usare i messaggi per addestrare modelli;
#   risposta entro 3 secondi con defer(); testo 2000/4096; tetto di
#   spesa (D13).
# Da chi prendere spunto: MEE6 (AI venduta a parte), Maki (AI nei piani
#   a pagamento).
# Dipende da: Privacy policy pubblicata con l'elenco dei fornitori.
#   Consenso dell'admin per server. message_content. D13.
#
# Prima di iniziare: lista di controllo di
#   revisione/01-analisi/LIMITI.md (Parte 4); ogni impostazione passa da
#   un solo punto del codice, usato anche dal pannello web (decisione
#   D16); prima il test che fallisce, poi il codice.
# Dettaglio: revisione/02-piano/NUOVE_FUNZIONI.md e il catalogo in
#   revisione/01-analisi/catalogo/.
# ----------------------------------------------------------------------
