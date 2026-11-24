"""
cogs/fun/creature.py
====================
Creature di fantasia (yokai e spiriti) e scontri con una posta in monete: /giochi sfide creature e scontro.
Le creature nascono dagli oggetti del negozio (/monete usa, ECO-101). Lo sfidato sceglie la sua creatura dal menu
(solo lui); posta, forze e storico passano in una sola transazione che controlla i saldi di entrambi.
Le monete del bot non si comprano con soldi veri.
Funzioni coperte: ECO-101
Dipende da: core/creature_logic.py, core/repositories/creature_repo.py
"""

from __future__ import annotations

import logging
import random

import discord
from discord import app_commands
from discord.ext import commands

from cogs.fun.sfide import SG_SFIDE
from core import creature_logic as cl
from core.command_groups import CogConGruppi, comando_di_gruppo, togli_comandi_del_cog
from core.database import db
from core.duello_logic import ATTESA_RISPOSTA, POSTA_MASSIMA, POSTA_MINIMA
from core.i18n import testo_per
from core.repositories.creature_repo import EsitoScontro, creature_repo
from core.repositories.leveling_settings_repo import leveling_settings_repo
from core.repositories.sociale_repo import sociale_repo
from core.ui_base import BaseView

logger = logging.getLogger("iyokai.creature")
NESSUNA_MENZIONE = discord.AllowedMentions.none()
RNG = random.SystemRandom()
ID_MASSIMO = 2_000_000_000


async def nome_creatura(interaction: discord.Interaction, specie: int, pubblica: bool = False) -> str:
    return await testo_per(interaction, f"crt_specie_{specie}", pubblica=pubblica)


class ScontroView(BaseView):
    """Lo sfidato sceglie una delle sue creature (lo scontro parte subito) o rifiuta; lo sfidante può annullare."""

    def __init__(
        self, guild_id: int, sfidante: discord.Member, creatura_sfidante: int, sfidato: discord.Member, posta: int, moneta: str,
        opzioni: list[tuple[int, str]],
    ) -> None:
        super().__init__(timeout=ATTESA_RISPOSTA)
        self.guild_id, self.sfidante, self.creatura_sfidante, self.sfidato = guild_id, sfidante, creatura_sfidante, sfidato
        self.posta, self.moneta = posta, moneta
        self._chiusa = False
        self.scegli.options = [discord.SelectOption(label=testo[:100], value=str(cid)) for cid, testo in opzioni[: cl.MAX_CREATURE]]

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not await super().interaction_check(interaction):
            return False
        if interaction.user.id not in (self.sfidato.id, self.sfidante.id):
            await interaction.response.send_message(await testo_per(interaction, "sfd_non_tuo"), ephemeral=True)
            return False
        return True

    async def _chiudi(self, interaction: discord.Interaction, testo: str) -> None:
        self._chiusa = True
        self.stop()
        for b in self.children:
            b.disabled = True
        await interaction.response.edit_message(content=testo, view=self, allowed_mentions=NESSUNA_MENZIONE)

    @discord.ui.select(placeholder="…", min_values=1, max_values=1, options=[discord.SelectOption(label="x", value="0")])
    async def scegli(self, interaction: discord.Interaction, select: discord.ui.Select) -> None:
        if interaction.user.id != self.sfidato.id:  # solo lo sfidato sceglie
            await interaction.response.send_message(await testo_per(interaction, "sfd_solo_sfidato"), ephemeral=True)
            return
        await self._scontra(interaction, int(select.values[0]))

    async def _scontra(self, interaction: discord.Interaction, creatura_id: int) -> None:
        if self._chiusa:  # nessun await tra controllo e segno: due clic non passano insieme
            await interaction.response.send_message(await testo_per(interaction, "leveling_gia_fatto"), ephemeral=True)
            return
        self._chiusa = True
        try:
            scontro = await creature_repo.scontra(
                self.guild_id, self.sfidante.id, self.creatura_sfidante, self.sfidato.id, creatura_id, self.posta, RNG
            )
        except Exception:
            self._chiusa = False
            raise
        self._chiusa = False  # _chiudi lo richiude
        if scontro.esito is EsitoScontro.CREATURA_NON_VALIDA:
            await self._chiudi(interaction, await testo_per(interaction, "crt_non_valida", pubblica=True))
            return
        if scontro.esito is not EsitoScontro.FATTO:
            chiave = "sfd_poche_sfidante" if scontro.esito is EsitoScontro.POCHE_SFIDANTE else "sfd_poche_sfidato"
            await self._chiudi(interaction, await testo_per(interaction, chiave, moneta=self.moneta, pubblica=True))
            return
        vincitore = self.sfidante if scontro.vince_sfidante else self.sfidato
        perdente = self.sfidato if scontro.vince_sfidante else self.sfidante
        testo = await testo_per(
            interaction, "crt_esito", vincitore=vincitore.mention, perdente=perdente.mention, importo=scontro.importo,
            moneta=self.moneta, forza_vinc=scontro.forza_vincitrice, forza_perd=scontro.forza_perdente, pubblica=True,
        )
        if scontro.perdente_persa:
            testo += "\n" + await testo_per(interaction, "crt_fuggita", perdente=perdente.mention, pubblica=True)
        await self._chiudi(interaction, testo)

    @discord.ui.button(label="Rifiuta", style=discord.ButtonStyle.danger)
    async def rifiuta(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self._chiusa:
            await interaction.response.send_message(await testo_per(interaction, "leveling_gia_fatto"), ephemeral=True)
            return
        await self._chiudi(interaction, await testo_per(interaction, "sfd_rifiutato", pubblica=True))


class CreatureCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._in_attesa: set[tuple[int, int]] = set()  # uno scontro aperto per sfidante

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

    @comando_di_gruppo("giochi", nome="creature", descrizione="Le tue creature di fantasia: forza e vittorie.", sottogruppo=SG_SFIDE)
    async def creature(self, interaction: discord.Interaction) -> None:
        if not await self._attivo(interaction):
            return
        righe = await creature_repo.elenco(interaction.guild.id, interaction.user.id)
        if not righe:
            await interaction.response.send_message(await testo_per(interaction, "crt_nessuna"), ephemeral=True)
            return
        elenco = []
        for r in righe:
            nome = await nome_creatura(interaction, r["specie"])
            elenco.append(await testo_per(interaction, "crt_riga", id=r["id"], nome=nome, forza=r["forza"], vinte=r["vittorie"], perse=r["sconfitte"]))
        testo = await testo_per(interaction, "crt_titolo", max=cl.MAX_CREATURE) + "\n" + "\n".join(elenco)
        await interaction.response.send_message(testo[:1900], ephemeral=True)

    @comando_di_gruppo("giochi", nome="scontro", descrizione="Fai combattere la tua creatura contro quella di un membro, con una posta.", sottogruppo=SG_SFIDE)
    @app_commands.describe(
        membro="Chi sfidi", posta=f"Monete in palio ({POSTA_MINIMA}-{POSTA_MASSIMA})",
        creatura="ID della tua creatura (vedi /giochi sfide creature); di base la più forte",
    )
    async def scontro(
        self, interaction: discord.Interaction, membro: discord.Member, posta: app_commands.Range[int, POSTA_MINIMA, POSTA_MASSIMA],
        creatura: app_commands.Range[int, 1, ID_MASSIMO] | None = None,
    ) -> None:
        if not await self._attivo(interaction):
            return
        if membro.id == interaction.user.id or membro.bot:
            await interaction.response.send_message(await testo_per(interaction, "sfd_bersaglio"), ephemeral=True)
            return
        if await sociale_repo.ha_bloccato(membro.id, interaction.user.id):  # ECO-155
            await interaction.response.send_message(await testo_per(interaction, "soc_bloccato"), ephemeral=True)
            return
        guild_id = interaction.guild.id
        mie = await creature_repo.elenco(guild_id, interaction.user.id)
        sua = next((r for r in mie if creatura is None or r["id"] == creatura), None)
        if sua is None:
            await interaction.response.send_message(await testo_per(interaction, "crt_nessuna" if not mie else "crt_non_tua"), ephemeral=True)
            return
        loro = await creature_repo.elenco(guild_id, membro.id)
        if not loro:
            await interaction.response.send_message(await testo_per(interaction, "crt_sfidato_nessuna"), ephemeral=True)
            return
        chiave = (guild_id, interaction.user.id)
        if chiave in self._in_attesa:
            await interaction.response.send_message(await testo_per(interaction, "sfd_gia_aperta"), ephemeral=True)
            return
        impostazioni = (await leveling_settings_repo.get_config(guild_id)).impostazioni
        opzioni = []
        for r in loro:
            nome = await nome_creatura(interaction, r["specie"], pubblica=True)
            opzioni.append((r["id"], await testo_per(interaction, "crt_opzione", nome=nome, forza=r["forza"], pubblica=True)))
        view = ScontroView(guild_id, interaction.user, sua["id"], membro, posta, impostazioni.currency_name, opzioni)
        view.scegli.placeholder = (await testo_per(interaction, "crt_scegli", pubblica=True))[:150]
        view.rifiuta.label = (await testo_per(interaction, "crt_rifiuta", pubblica=True))[:80]
        nome_mia = await nome_creatura(interaction, sua["specie"], pubblica=True)
        self._in_attesa.add(chiave)
        try:
            await interaction.response.send_message(
                await testo_per(
                    interaction, "crt_sfida", sfidante=interaction.user.mention, sfidato=membro.mention, nome=nome_mia,
                    forza=sua["forza"], posta=posta, moneta=impostazioni.currency_name, pubblica=True,
                ),
                view=view,
                allowed_mentions=discord.AllowedMentions(users=[membro]),
            )
            await view.wait()
        finally:
            self._in_attesa.discard(chiave)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(CreatureCog(bot))
