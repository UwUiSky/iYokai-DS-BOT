"""
cogs/utility/embed_builder.py
=============================
Comandi e modulo di composizione.
Funzioni coperte: SPEC §22 (NF-17)

STATO: scheletro. Il codice non è ancora scritto (issue #88).
"""

# ----------------------------------------------------------------------
# NOTA PER CHI SCRIVE QUESTO FILE — issue #88, fase F9
# Funzione: NF-17, Costruttore di embed.
#
# Cosa deve fare la funzione: Un admin compone un messaggio con titolo,
#   testo, colore, immagine e campi, lo vede in anteprima e lo pubblica
#   o lo modifica dopo.
# Questo file: Comandi e modulo di composizione.
# Comandi previsti: /admin embed crea|modifica|pubblica|elenco.
# File collegati: core/embed_builder_logic.py,
#   core/repositories/saved_embed_repo.py.
# Test da scrivere per primi: tests/test_embed_builder.py.
# Migrazione: core/migrations/NNNN_saved_embeds.sql. (prossimo numero
#   libero in core/migrations/).
# Limiti da rispettare: Tutti i limiti degli embed (256, 4096, 1024, 25,
#   6000) controllati al salvataggio.
# Da chi prendere spunto: ProBot, Atlas, Hydra ("message builder"),
#   Carl-bot.
# Dipende da: Nessuna. L'editor visuale arriva con il pannello web.
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
