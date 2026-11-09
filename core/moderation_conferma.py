"""
core/moderation_conferma.py
===========================
Conferma a due tasti prima di una sanzione (MOD-066) e risposta compatta o cancellata dopo qualche secondo
(MOD-067). I comandi di sanzione chiamano `conferma_sanzione` dopo i controlli e `invia_esito` per rispondere.
Funzioni coperte: SPEC §5.13 (MOD-066, MOD-067)
Dipende da: core/moderation_risposte.py, core/moderation_opzioni.py
"""

from __future__ import annotations

import asyncio
import contextvars
import logging

import discord

from cogs.moderation._shared import check_can_moderate
from core import moderation_opzioni, moderation_risposte as risposte
from core.command_access import Livello, puo_usare
from core.i18n import testo_per
from core.ui_base import BaseView

logger = logging.getLogger(__name__)

# Chi ha già chiesto conferma (es. «applica» di un motivo pronto) non la fa chiedere una seconda volta.
GIA_CONFERMATA: contextvars.ContextVar[bool] = contextvars.ContextVar("sanzione_gia_confermata", default=False)
_cancellazioni: set[asyncio.Task] = set()


class ConfermaSanzione(BaseView):
    """Due tasti, un solo clic valido, solo per chi ha dato il comando; scade in 60 secondi."""

    def __init__(self, autore_id: int) -> None:
        super().__init__(timeout=risposte.SECONDI_CONFERMA)
        self.autore_id = autore_id
        self.esito: bool | None = None  # None = scaduta
        self.interazione: discord.Interaction | None = None
        self._partita = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not await super().interaction_check(interaction):
            return False
        if interaction.user.id != self.autore_id:
            await interaction.response.send_message(await testo_per(interaction, "conferma_solo_chi_comanda"), ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Conferma", style=discord.ButtonStyle.danger)
    async def conferma(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self._partita:  # segnato prima di ogni await: un doppio clic dà una sola sanzione
            return
        self._partita = True
        self.esito, self.interazione = True, interaction
        self.stop()

    @discord.ui.button(label="Annulla", style=discord.ButtonStyle.secondary)
    async def annulla(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self._partita:
            return
        self._partita = True
        self.esito = False
        self.stop()
        await interaction.response.defer()


async def conferma_sanzione(
    interaction: discord.Interaction, membro: discord.Member, azione: str, motivo: str | None, *, livello: Livello
) -> discord.Interaction | None:
    """
    Se il server vuole la conferma, la chiede al moderatore con un messaggio solo suo. Restituisce l'interazione
    con cui il comando deve continuare (quella del tasto Conferma; senza conferma, la stessa di prima) oppure None
    se ha annullato, è scaduta o livello e gerarchia sono cambiati nel frattempo.
    """
    if GIA_CONFERMATA.get() or not (await moderation_opzioni.leggi(interaction.guild.id)).conferma:
        return interaction
    vista = ConfermaSanzione(interaction.user.id)
    domanda = await testo_per(
        interaction, "conferma_domanda", azione=azione, utente=membro.mention, motivo=(motivo or "-")[:300]
    )
    await interaction.response.send_message(
        domanda[:2000], view=vista, ephemeral=True, allowed_mentions=discord.AllowedMentions.none()
    )
    await vista.wait()
    chiave = {True: "conferma_in_corso", False: "conferma_annullata", None: "conferma_scaduta"}[vista.esito]
    try:
        await interaction.edit_original_response(content=await testo_per(interaction, chiave), view=None)
    except discord.HTTPException:
        pass
    if not vista.esito:
        return None
    nuova = vista.interazione
    # Tra la domanda e il clic il livello o i ruoli possono cambiare: si ricontrolla tutto.
    if not await puo_usare(nuova, livello):
        chiave = "motivopronto_serve_modban" if livello is Livello.MODBAN else "motivopronto_serve_mod"
        await nuova.response.send_message(await testo_per(nuova, chiave), ephemeral=True)
        return None
    if not await check_can_moderate(nuova, membro):
        return None
    return nuova


def _campi(embed: discord.Embed) -> dict[str, str]:
    return {c.name: c.value for c in embed.fields}


async def invia_esito(
    interaction: discord.Interaction, embed: discord.Embed, *, seguito: bool, nota: str | None = None
) -> None:
    """
    Risponde al moderatore con l'esito. Normale: il riquadro di sempre. Compatta e cancella-dopo: una riga.
    Cancella-dopo toglie il messaggio dopo N secondi (solo finché il token vale). `seguito` dice se il comando
    ha già risposto o rimandato (defer): allora si usa il seguito, altrimenti la risposta.
    """
    o = await moderation_opzioni.leggi(interaction.guild.id)
    if risposte.compatta(o.risposte):
        riga = risposte.riga_compatta(embed.title, _campi(embed), nota=nota)
        corpo = {"content": riga, "allowed_mentions": discord.AllowedMentions.none()}
    else:
        if nota:
            embed.set_footer(text=nota)
        corpo = {"embed": embed}
    cancella = o.risposte == risposte.MODO_CANCELLA_DOPO and risposte.puo_cancellare(o.risposte_secondi)
    messaggio = None
    if seguito:
        messaggio = await interaction.followup.send(**corpo, **({"wait": True} if cancella else {}))
    else:
        await interaction.response.send_message(**corpo)
        if cancella:
            messaggio = await interaction.original_response()
    if cancella and messaggio is not None:
        task = asyncio.create_task(_cancella_dopo(messaggio, o.risposte_secondi))
        _cancellazioni.add(task)
        task.add_done_callback(_cancellazioni.discard)


async def _cancella_dopo(messaggio, secondi: int) -> None:
    await asyncio.sleep(secondi)
    try:
        await messaggio.delete()
    except discord.HTTPException:
        logger.debug("Risposta di moderazione già cancellata o non più cancellabile")
