"""
cogs/utility/birthdays.py
=========================
Comandi dei compleanni.
Funzioni coperte: SPEC §23 (NF-26)

STATO: scheletro. Il codice non è ancora scritto (issue #97).
"""

# ----------------------------------------------------------------------
# NOTA PER CHI SCRIVE QUESTO FILE — issue #97, fase F13
# Funzione: NF-26, Compleanni.
#
# Cosa deve fare la funzione: Ogni utente registra il suo compleanno. Il
#   giorno giusto il bot fa gli auguri in un canale e può dare un ruolo
#   per 24 ore.
# Questo file: Comandi dei compleanni.
# Comandi previsti: /level compleanno imposta|rimuovi, /admin compleanni
#   canale|ruolo.
# File collegati: core/birthday_logic.py, core/birthday_worker.py,
#   core/repositories/birthday_repo.py.
# Test da scrivere per primi: tests/test_birthdays.py.
# Migrazione: core/migrations/NNNN_birthdays.sql. (prossimo numero
#   libero in core/migrations/).
# Limiti da rispettare: Solo giorno e mese (niente anno: meno dati
#   personali); dato cancellabile dall'utente.
# Da chi prendere spunto: MEE6, Maki, Lawliet.
# Dipende da: NF-04 (dato personale).
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
