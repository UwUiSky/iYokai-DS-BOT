"""
cogs/utility/starboard.py
=========================
Comandi e ascolto delle reazioni.
Funzioni coperte: SPEC §22 (NF-08)

STATO: scheletro. Il codice non è ancora scritto (issue #79).
"""

# ----------------------------------------------------------------------
# NOTA PER CHI SCRIVE QUESTO FILE — issue #79, fase F9
# Funzione: NF-08, Starboard.
#
# Cosa deve fare la funzione: Un messaggio che riceve abbastanza ⭐ viene
#   copiato in un canale "bacheca".
# Questo file: Comandi e ascolto delle reazioni.
# Comandi previsti: /admin starboard imposta|soglia|disattiva.
# File collegati: core/starboard_logic.py,
#   core/repositories/starboard_repo.py.
# Test da scrivere per primi: tests/test_starboard.py.
# Migrazione: core/migrations/NNNN_starboard.sql. (prossimo numero
#   libero in core/migrations/).
# Limiti da rispettare: Embed entro i limiti; un solo messaggio in
#   bacheca per originale; canali NSFW esclusi di default.
# Da chi prendere spunto: MEE6 (gratis), Carl-bot, Dyno, Zeppelin,
#   Circle.
# Dipende da: NF-01 per il canale.
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
