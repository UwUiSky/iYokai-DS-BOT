"""
cogs/utility/invites.py
=======================
Comandi degli inviti.
Funzioni coperte: SPEC §23 (NF-27)

STATO: scheletro. Il codice non è ancora scritto (issue #98).
"""

# ----------------------------------------------------------------------
# NOTA PER CHI SCRIVE QUESTO FILE — issue #98, fase F13
# Funzione: NF-27, Inviti: comando e classifica.
#
# Cosa deve fare la funzione: Ogni membro vede quante persone ha
#   invitato. Classifica degli inviti del server.
# Questo file: Comandi degli inviti.
# Comandi previsti: /level inviti, /level leaderboard tipo:inviti.
# File collegati: core/repositories/invite_stats_repo.py.
# File esistenti da toccare: core/invite_tracker.py.
# Test da scrivere per primi: tests/test_invites.py.
# Migrazione: core/migrations/NNNN_invite_stats.sql. (prossimo numero
#   libero in core/migrations/).
# Limiti da rispettare: Classifica di 10 righe; l'attribuzione sbaglia
#   con ingressi simultanei (LC-6): va detto all'utente.
# Da chi prendere spunto: MEE6, Maki, Lawliet.
# Dipende da: LC-6 sistemato.
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
