"""
cogs/utility/autoresponder.py
=============================
Ascolta i messaggi e risponde.
Funzioni coperte: SPEC §14.7 (NF-10)

STATO: scheletro. Il codice non è ancora scritto (issue #81).
"""

# ----------------------------------------------------------------------
# NOTA PER CHI SCRIVE QUESTO FILE — issue #81, fase F9
# Funzione: NF-10, Risposte automatiche.
#
# Cosa deve fare la funzione: Quando un messaggio contiene una parola o
#   frase scelta, il bot risponde da solo. Con condizioni: canale,
#   ruolo, corrispondenza esatta o parziale.
# Questo file: Ascolta i messaggi e risponde.
# Comandi previsti: /admin comandi risposta-crea|risposta-
#   elimina|risposte.
# File collegati: core/autoresponder_logic.py,
#   core/repositories/autoresponder_repo.py.
# Test da scrivere per primi: tests/test_autoresponder.py.
# Migrazione: core/migrations/NNNN_autoresponder.sql. (prossimo numero
#   libero in core/migrations/).
# Limiti da rispettare: Tetto per server; pausa per canale; mai
#   rispondere ai bot; testo 2000.
# Da chi prendere spunto: Carl-bot ("trigger": 50 gratis), YAGPDB.
# Dipende da: message_content (D9). NF-09 (stessa tabella di base).
#
# Prima di iniziare: lista di controllo di
#   revisione/01-analisi/LIMITI.md (Parte 4); ogni impostazione passa da
#   un solo punto del codice, usato anche dal pannello web (decisione
#   D16); prima il test che fallisce, poi il codice.
# Dettaglio: revisione/02-piano/NUOVE_FUNZIONI.md e il catalogo in
#   revisione/01-analisi/catalogo/.
# ----------------------------------------------------------------------

from discord.ext import commands


async def setup(bot: commands.Bot) -> None:
    """Scheletro: non registra nessun comando finché la funzione non viene scritta."""
