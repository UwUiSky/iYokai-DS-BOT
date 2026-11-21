"""
cogs/fun/sfide.py
=================
Sfide tra utenti con una posta in monete: /giochi sfide duello e duelli. Lo sfidato accetta con un
bottone che solo lui può premere; la posta passa dal perdente al vincitore in una sola transazione che
controlla i saldi di entrambi. Le monete del bot non si comprano con soldi veri.
Funzioni coperte: ECO-104, ECO-106
Dipende da: core/duello_logic.py, core/repositories/duelli_repo.py
"""

from __future__ import annotations

import logging
import random

import discord
from discord import app_commands
from discord.ext import commands

from core.command_groups import CogConGruppi, comando_di_gruppo, togli_comandi_del_cog
from core.database import db
from core.duello_logic import ATTESA_RISPOSTA, POSTA_MASSIMA, POSTA_MINIMA, lancia_duello
from core.i18n import testo_per
from core.repositories.duelli_repo import EsitoPosta, duelli_repo
from core.repositories.leveling_settings_repo import leveling_settings_repo
from core.repositories.sociale_repo import sociale_repo
from core.ui_base import BaseView

logger = logging.getLogger("iyokai.sfide")
NESSUNA_MENZIONE = discord.AllowedMentions.none()
RNG = random.SystemRandom()
SG_SFIDE = ("sfide", "Duelli e partite a più passi con le monete")


class DuelloView(BaseView):
    """Accetta/Rifiuta per lo sfidato, Annulla per lo sfidante. Vale una sola volta."""

    def __init__(self, guild_id: int, sfidante: discord.Member, sfidato: discord.Member, posta: int, moneta: str) -> None:
        super().__init__(timeout=ATTESA_RISPOSTA)
        self.guild_id, self.sfidante, self.sfidato, self.posta, self.moneta = guild_id, sfidante, sfidato, posta, moneta
        self._chiusa = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not await super().interaction_check(interaction):
            return False
        if interaction.user.id not in (self.sfidato.id, self.sfidante.id):
            await interaction.response.send_message(await testo_per(interaction, "sfd_non_tuo"), ephemeral=True)
            return False
        return True

    async def _chiudi(self, interaction: discord.Interaction, testo: str, embed: discord.Embed | None = None) -> None:
        self._chiusa = True
        self.stop()
        for b in self.children:
            b.disabled = True
        await interaction.response.edit_message(content=testo, embed=embed, view=self, allowed_mentions=NESSUNA_MENZIONE)

    @discord.ui.button(label="Accetta", style=discord.ButtonStyle.success)
    async def accetta(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if interaction.user.id != self.sfidato.id:  # solo lo sfidato accetta
            await interaction.response.send_message(await testo_per(interaction, "sfd_solo_sfidato"), ephemeral=True)
            return
        if self._chiusa:  # nessun await tra controllo e segno: due clic non passano insieme
            await interaction.response.send_message(await testo_per(interaction, "leveling_gia_fatto"), ephemeral=True)
            return
        self._chiusa = True
        esito = lancia_duello(RNG)
        passaggio = await duelli_repo.regola(self.guild_id, self.sfidante.id, self.sfidato.id, esito.vince_sfidante, self.posta)
        self._chiusa = False  # _chiudi lo richiude
        if passaggio.esito is not EsitoPosta.FATTO:
            chiave = "sfd_poche_sfidante" if passaggio.esito is EsitoPosta.SFIDANTE_POCHE else "sfd_poche_sfidato"
            await self._chiudi(interaction, await testo_per(interaction, chiave, moneta=self.moneta, pubblica=True))
            return
        vincitore = self.sfidante if esito.vince_sfidante else self.sfidato
        riga = f"{self.sfidante.display_name[:30]}: {' + '.join(map(str, esito.tiri_sfidante))} = **{sum(esito.tiri_sfidante)}**\n" \
               f"{self.sfidato.display_name[:30]}: {' + '.join(map(str, esito.tiri_sfidato))} = **{sum(esito.tiri_sfidato)}**"
        testo = await testo_per(
            interaction, "sfd_esito", vincitore=vincitore.mention, importo=passaggio.importo, moneta=self.moneta, tiri=riga, pubblica=True
        )
        await self._chiudi(interaction, testo)

    @discord.ui.button(label="Rifiuta", style=discord.ButtonStyle.danger)
    async def rifiuta(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self._chiusa:
            await interaction.response.send_message(await testo_per(interaction, "leveling_gia_fatto"), ephemeral=True)
            return
        await self._chiudi(interaction, await testo_per(interaction, "sfd_rifiutato", pubblica=True))


class SfideCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._in_attesa: set[tuple[int, int]] = set()  # una sfida aperta per sfidante

    def cog_unload(self) -> None:
        togli_comandi_del_cog(self)

    async def _attivo(self, interaction: discord.Interaction) -> bool:
        if interaction.guild is None:
            await interaction.response.send_message(await testo_per(interaction, "guild_only_command"), ephemeral=True)
            return False
        for modulo in ("fun", "leveling"):
            if not await db.is_module_active_for_guild(interaction.guild.id, modulo):
                await interaction.response.send_message(await testo_per(interaction, "ping_questo_modulo_non_attivo_su"), ephemeral=True)
                return False
        return True

    @comando_di_gruppo("giochi", nome="duello", descrizione="Sfida un membro a duello: chi vince prende la posta.", sottogruppo=SG_SFIDE)
    @app_commands.describe(membro="Chi sfidi", posta=f"Monete in palio ({POSTA_MINIMA}-{POSTA_MASSIMA})")
    async def duello(
        self, interaction: discord.Interaction, membro: discord.Member, posta: app_commands.Range[int, POSTA_MINIMA, POSTA_MASSIMA]
    ) -> None:
        if not await self._attivo(interaction):
            return
        if membro.id == interaction.user.id or membro.bot:
            await interaction.response.send_message(await testo_per(interaction, "sfd_bersaglio"), ephemeral=True)
            return
        if await sociale_repo.ha_bloccato(membro.id, interaction.user.id):  # ECO-155
            await interaction.response.send_message(await testo_per(interaction, "soc_bloccato"), ephemeral=True)
            return
        impostazioni = (await leveling_settings_repo.get_config(interaction.guild.id)).impostazioni
        chiave = (interaction.guild.id, interaction.user.id)
        if chiave in self._in_attesa:
            await interaction.response.send_message(await testo_per(interaction, "sfd_gia_aperta"), ephemeral=True)
            return
        view = DuelloView(interaction.guild.id, interaction.user, membro, posta, impostazioni.currency_name)
        self._in_attesa.add(chiave)
        try:
            await interaction.response.send_message(
                await testo_per(
                    interaction, "sfd_sfida", sfidante=interaction.user.mention, sfidato=membro.mention,
                    posta=posta, moneta=impostazioni.currency_name, pubblica=True,
                ),
                view=view,
                allowed_mentions=discord.AllowedMentions(users=[membro]),
            )
            await view.wait()
        finally:
            self._in_attesa.discard(chiave)

    @comando_di_gruppo("giochi", nome="duelli", descrizione="Classifica dei duelli e i tuoi ultimi.", sottogruppo=SG_SFIDE)
    async def duelli(self, interaction: discord.Interaction) -> None:
        if not await self._attivo(interaction):
            return
        g, u = interaction.guild.id, interaction.user.id
        top = await duelli_repo.classifica(g)
        mio = await duelli_repo.storico(g, u, 5)
        if not top and not mio:
            await interaction.response.send_message(await testo_per(interaction, "gm_nessuna_partita"), ephemeral=True)
            return
        righe = [f"{n}. <@{r['user_id']}> — {r['vinti']}V {r['persi']}S ({r['netto']:+d})" for n, r in enumerate(top, 1)]
        mie = [f"{'🏆' if r['vincitore'] == u else '💀'} {r['posta']}" for r in mio]
        testo = "\n".join(righe) + ("\n\n" + " ".join(mie) if mie else "")
        await interaction.response.send_message(testo[:3900], allowed_mentions=NESSUNA_MENZIONE)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(SfideCog(bot))
