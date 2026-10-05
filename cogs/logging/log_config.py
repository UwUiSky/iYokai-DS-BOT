"""
cogs/logging/log_config.py
==========================
Comandi per scegliere o creare i canali dei log.
Funzioni coperte: SPEC §18 (NF-01)

STATO: scheletro. Il codice non è ancora scritto (issue #72).
"""

# ----------------------------------------------------------------------
# NOTA PER CHI SCRIVE QUESTO FILE — issue #72, fase F6
# Funzione: NF-01, Router dei canali e log su forum.
#
# Cosa deve fare la funzione: Un solo punto che decide dove scrive il
#   bot. Per ogni tipo di uscita (log membri, log messaggi, moderazione,
#   voce, server, automod, allarmi, benvenuto…) si sceglie un canale di
#   testo o un forum. Nel forum il bot usa un post per tipo di log (D3).
#   Se il canale sparisce, avvisa gli admin una volta sola.
# Questo file: Comandi per scegliere o creare i canali dei log.
# Comandi previsti: /log canale, /log crea-canali, /log crea-forum, /log
#   stato, /log ignora …. Fino a F7 vivono nel gruppo esistente /logs.
# File collegati: core/channel_router.py,
#   core/repositories/output_channel_repo.py.
# Test da scrivere per primi: tests/test_channel_router.py.
# Migrazione: core/migrations/NNNN_output_channels.sql. (prossimo numero
#   libero in core/migrations/).
# Limiti da rispettare: 50 canali per categoria; 500 per server; nome
#   100; HTTPException sempre catturata; canali ___hidden___ ignorati
#   (LIM-38).
# Da chi prendere spunto: Carl-bot (log aio crea categoria e 5 canali),
#   Wick (crea #logs e #modlogs).
# Dipende da: Migrazioni versionate (fatte). REVIEW.md §8.
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
