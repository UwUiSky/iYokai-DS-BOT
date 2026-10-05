"""
cogs/fun/soundboard.py
======================
Comando dei suoni.
Funzioni coperte: SPEC §23 (NF-35)

STATO: scheletro. Il codice non è ancora scritto (issue #106).
"""

# ----------------------------------------------------------------------
# NOTA PER CHI SCRIVE QUESTO FILE — issue #106, fase F13
# Funzione: NF-35, Effetti sonori in vocale.
#
# Cosa deve fare la funzione: Brevi suoni da far partire in un canale
#   vocale.
# Questo file: Comando dei suoni.
# Comandi previsti: /fun suono.
# Test da scrivere per primi: tests/test_soundboard_play.py.
# Limiti da rispettare: Usa un bot musicale libero; pausa per utente.
# Da chi prendere spunto: Yggdrasil (19 suoni), YAGPDB.
# Dipende da: F2 finita.
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
