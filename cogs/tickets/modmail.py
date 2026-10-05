"""
cogs/tickets/modmail.py
=======================
Ticket aperti in DM.
Funzioni coperte: SPEC §23 (NF-33)

STATO: scheletro. Il codice non è ancora scritto (issue #104).
"""

# ----------------------------------------------------------------------
# NOTA PER CHI SCRIVE QUESTO FILE — issue #104, fase F13
# Funzione: NF-33, Ticket via messaggio privato.
#
# Cosa deve fare la funzione: L'utente scrive in DM al bot e nasce un
#   canale per lo staff. Lo staff risponde da lì, anche in forma
#   anonima.
# Questo file: Ticket aperti in DM.
# Comandi previsti: /admin ticket dm attiva|disattiva.
# File collegati: core/modmail_logic.py,
#   core/repositories/modmail_repo.py.
# Test da scrivere per primi: tests/test_modmail.py.
# Migrazione: core/migrations/NNNN_modmail.sql. (prossimo numero libero
#   in core/migrations/).
# Limiti da rispettare: Un solo ciclo sui DM (oggi lo usa lo spam-trap):
#   un punto di ingresso comune.
# Da chi prendere spunto: ModMail.
# Dipende da: message_content. NF-30 (stesso ingresso dei DM).
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
