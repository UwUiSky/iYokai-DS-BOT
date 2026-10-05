"""
core/repositories/custom_command_repo.py
========================================
Tag salvati per server.
Funzioni coperte: SPEC §22 (NF-09)

STATO: scheletro. Il codice non è ancora scritto (issue #80).
"""

# ----------------------------------------------------------------------
# NOTA PER CHI SCRIVE QUESTO FILE — issue #80, fase F9
# Funzione: NF-09, Comandi personalizzati (tag).
#
# Cosa deve fare la funzione: Ogni server crea i suoi comandi: un nome,
#   un testo o un embed, un ruolo da dare o togliere, una pausa tra un
#   uso e l'altro. Si usano con /utility tag <nome> e, se l'admin vuole,
#   anche con un prefisso scelto dal server (solo per i tag: è
#   l'alternativa al "prefisso personalizzato" di SPEC §2.4).
# Questo file: Tag salvati per server.
# Comandi previsti: /admin comandi crea|modifica|elimina|elenco,
#   /utility tag.
# File collegati: cogs/utility/custom_commands.py,
#   core/custom_command_logic.py.
# File esistenti da toccare: cogs/utility/custom_command_requests.py
#   resta (richieste all'owner).
# Test da scrivere per primi: tests/test_custom_commands.py.
# Migrazione: core/migrations/NNNN_custom_commands.sql. (prossimo numero
#   libero in core/migrations/).
# Limiti da rispettare: Testo 2000; nome 32; tetto per server (es. 50
#   gratis); nessun str.format (si usa core/template_renderer.py); ruoli
#   con check_role_assignable.
# Da chi prendere spunto: YAGPDB (100 gratis), Carl-bot (tag), MEE6.
# Dipende da: message_content solo per l'uso con prefisso.
#
# Prima di iniziare: lista di controllo di
#   revisione/01-analisi/LIMITI.md (Parte 4); ogni impostazione passa da
#   un solo punto del codice, usato anche dal pannello web (decisione
#   D16); prima il test che fallisce, poi il codice.
# Dettaglio: revisione/02-piano/NUOVE_FUNZIONI.md e il catalogo in
#   revisione/01-analisi/catalogo/.
# ----------------------------------------------------------------------
