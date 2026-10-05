"""
cogs/logging/message_logs.py
============================
Ascolta cancellazioni e modifiche e le manda al router.
Funzioni coperte: SPEC §8.16 (NF-02)

STATO: scheletro. Il codice non è ancora scritto (issue #73).
"""

# ----------------------------------------------------------------------
# NOTA PER CHI SCRIVE QUESTO FILE — issue #73, fase F6
# Funzione: NF-02, Log dei messaggi cancellati, modificati e cancellati
#   in blocco.
#
# Cosa deve fare la funzione: Quando un messaggio viene cancellato o
#   modificato, il bot lo scrive nel log con autore, canale e testo di
#   prima e dopo. Una cancellazione in blocco produce un solo riepilogo
#   con un file.
# Questo file: Ascolta cancellazioni e modifiche e le manda al router.
# Comandi previsti: Nessun comando nuovo: si configura con /log canale
#   tipo:messaggi e /log ignora.
# File collegati: core/message_log_logic.py.
# Test da scrivere per primi: tests/test_message_logs.py.
# Limiti da rispettare: Campo 1024 e descrizione 4096: testo tagliato;
#   file sotto 10 MiB (LIM-55); cache dei messaggi limitata
#   (BoundedCache).
# Da chi prendere spunto: Carl-bot e Dyno. Carl-bot permette di ignorare
#   canali, utenti e prefissi.
# Dipende da: message_content attivo nel Portal (D9). NF-01.
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
