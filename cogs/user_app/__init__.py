"""
cogs/user_app/__init__.py
=========================
Pacchetto dei comandi personali.
Funzioni coperte: SPEC §B (NF-36)

STATO: scheletro. Il codice non è ancora scritto (issue #107).
"""

# ----------------------------------------------------------------------
# NOTA PER CHI SCRIVE QUESTO FILE — issue #107, fase F13
# Funzione: NF-36, Applicazione installabile dall'utente.
#
# Cosa deve fare la funzione: Comandi personali che l'utente porta con
#   sé in qualsiasi server e in DM: promemoria, profilo, utilità.
# Questo file: Pacchetto dei comandi personali.
# Comandi previsti: Comandi dell'applicazione utente (albero separato).
# File collegati: cogs/user_app/personal.py.
# Test da scrivere per primi: tests/test_user_app.py.
# Limiti da rispettare: 5 risposte successive per interazione dove l'app
#   non è installata nel server.
# Da chi prendere spunto: Nighty (solo l'idea lecita: comandi ovunque).
# Dipende da: NF-05.
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
