"""
cogs/leveling/sociale.py
========================
Amici, blocchi, matrimonio, prestigio e azzeramento dei propri dati di gioco: /level sociale ... e
/monete conto prestigio. Ogni richiesta (amicizia, matrimonio) si accetta con un bottone che solo il destinatario può
premere; chi ha bloccato qualcuno non riceve da lui richieste, regali, pagamenti o sfide.
Funzioni coperte: ECO-148, ECO-149, ECO-153, ECO-154, ECO-155, ECO-159
Dipende da: core/repositories/sociale_repo.py
"""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from cogs.leveling.leveling import _comando_rifiutato
from cogs.leveling.rischio import _SG_CONTO
from core.command_groups import CogConGruppi, comando_di_gruppo, togli_comandi_del_cog
from core.i18n import testo_per
from core.repositories.leveling_settings_repo import leveling_settings_repo
from core.repositories.sociale_repo import BONUS_PRESTIGIO, COSTO_MATRIMONIO, sociale_repo
from core.ui_base import BaseView

logger = logging.getLogger("iyokai.sociale")
NESSUNA_MENZIONE = discord.AllowedMentions.none()
SG_SOCIALE = ("sociale", "Amici, blocchi, matrimonio e dati di gioco")
PAROLA_AZZERA = "AZZERA"


class RichiestaView(BaseView):
    """Accetta/Rifiuta: solo il destinatario preme e vale una volta sola."""

    def __init__(self, mittente: discord.Member, destinatario: discord.Member, azione) -> None:
        super().__init__(timeout=120)
        self.mittente, self.destinatario, self.azione = mittente, destinatario, azione
        self._chiusa = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not await super().interaction_check(interaction):
            return False
        if interaction.user.id != self.destinatario.id:
            await interaction.response.send_message(await testo_per(interaction, "soc_non_tua"), ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Accetta", style=discord.ButtonStyle.success)
    async def accetta(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self._chiusa:  # nessun await tra controllo e segno
            await interaction.response.send_message(await testo_per(interaction, "leveling_gia_fatto"), ephemeral=True)
            return
        self._chiusa = True
        self.stop()
        chiave = await self.azione()
        await interaction.response.edit_message(
            content=await testo_per(interaction, chiave, mittente=self.mittente.mention, destinatario=self.destinatario.mention, pubblica=True),
            view=None, allowed_mentions=NESSUNA_MENZIONE,
        )

    @discord.ui.button(label="Rifiuta", style=discord.ButtonStyle.danger)
    async def rifiuta(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self._chiusa:
            await interaction.response.send_message(await testo_per(interaction, "leveling_gia_fatto"), ephemeral=True)
            return
        self._chiusa = True
        self.stop()
        await interaction.response.edit_message(content=await testo_per(interaction, "sfd_rifiutato", pubblica=True), view=None)


class SocialeCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    def cog_unload(self) -> None:
        togli_comandi_del_cog(self)

    async def _bersaglio_valido(self, interaction: discord.Interaction, membro: discord.Member) -> bool:
        if membro.id == interaction.user.id or membro.bot:
            await interaction.response.send_message(await testo_per(interaction, "sfd_bersaglio"), ephemeral=True)
            return False
        if await sociale_repo.ha_bloccato(membro.id, interaction.user.id):  # ECO-155
            await interaction.response.send_message(await testo_per(interaction, "soc_bloccato"), ephemeral=True)
            return False
        return True

    # ---------------------------------------------------------------- blocchi
    @comando_di_gruppo("level", nome="blocca", descrizione="Blocca un utente: niente richieste, regali, pagamenti o sfide da lui.", sottogruppo=SG_SOCIALE)
    @app_commands.describe(membro="Chi blocchi")
    async def blocca(self, interaction: discord.Interaction, membro: discord.Member) -> None:
        if await _comando_rifiutato(interaction):
            return
        if membro.id == interaction.user.id:
            await interaction.response.send_message(await testo_per(interaction, "sfd_bersaglio"), ephemeral=True)
            return
        esito = await sociale_repo.blocca(interaction.user.id, membro.id)
        await interaction.response.send_message(await testo_per(interaction, f"soc_blocca_{esito}"), ephemeral=True)

    @comando_di_gruppo("level", nome="sblocca", descrizione="Togli un utente dai bloccati (senza nome: l'elenco dei bloccati).", sottogruppo=SG_SOCIALE)
    @app_commands.describe(membro="Chi sblocchi")
    async def sblocca(self, interaction: discord.Interaction, membro: discord.Member | None = None) -> None:
        if await _comando_rifiutato(interaction):
            return
        if membro is None:
            ids = await sociale_repo.elenco_blocchi(interaction.user.id)
            testo = " ".join(f"<@{i}>" for i in ids) if ids else await testo_per(interaction, "soc_nessuno")
            await interaction.response.send_message(testo[:1900], ephemeral=True, allowed_mentions=NESSUNA_MENZIONE)
            return
        fatto = await sociale_repo.sblocca(interaction.user.id, membro.id)
        await interaction.response.send_message(await testo_per(interaction, "soc_sbloccato" if fatto else "soc_nessuno"), ephemeral=True)

    # ---------------------------------------------------------------- amici
    @comando_di_gruppo("level", nome="amico", descrizione="Chiedi a un membro di diventare tuo amico (tra amici i pagamenti non hanno tassa).", sottogruppo=SG_SOCIALE)
    @app_commands.describe(membro="A chi lo chiedi")
    async def amico(self, interaction: discord.Interaction, membro: discord.Member) -> None:
        if await _comando_rifiutato(interaction) or not await self._bersaglio_valido(interaction, membro):
            return
        g = interaction.guild.id

        async def accetta() -> str:
            esito = await sociale_repo.aggiungi_amico(g, interaction.user.id, membro.id)
            return {"ok": "soc_amici_ok", "gia": "soc_amici_gia", "pieno": "soc_amici_pieno"}[esito]

        view = RichiestaView(interaction.user, membro, accetta)
        await interaction.response.send_message(
            await testo_per(interaction, "soc_amici_richiesta", mittente=interaction.user.mention, destinatario=membro.mention, pubblica=True),
            view=view, allowed_mentions=discord.AllowedMentions(users=[membro]),
        )

    @comando_di_gruppo("level", nome="amici", descrizione="I tuoi amici, e togline uno.", sottogruppo=SG_SOCIALE)
    @app_commands.describe(togli="Un amico da togliere")
    async def amici(self, interaction: discord.Interaction, togli: discord.Member | None = None) -> None:
        if await _comando_rifiutato(interaction):
            return
        g, u = interaction.guild.id, interaction.user.id
        if togli is not None and togli.id != u:
            await sociale_repo.togli_amico(g, u, togli.id)
        ids = await sociale_repo.amici_di(g, u)
        await interaction.response.send_message(
            (" ".join(f"<@{i}>" for i in ids) if ids else await testo_per(interaction, "soc_nessuno"))[:1900], ephemeral=True, allowed_mentions=NESSUNA_MENZIONE
        )

    # ---------------------------------------------------------------- matrimonio
    @comando_di_gruppo("level", nome="sposa", descrizione=f"Proponi il matrimonio ({COSTO_MATRIMONIO} monete a testa alla cassa); va mantenuto.", sottogruppo=SG_SOCIALE)
    @app_commands.describe(membro="A chi lo proponi")
    async def sposa(self, interaction: discord.Interaction, membro: discord.Member) -> None:
        if await _comando_rifiutato(interaction) or not await self._bersaglio_valido(interaction, membro):
            return
        g = interaction.guild.id

        async def accetta() -> str:
            esito = await sociale_repo.sposa(g, interaction.user.id, membro.id)
            return {"ok": "soc_sposi_ok", "gia": "soc_sposi_gia", "poche": "soc_sposi_poche"}[esito]

        view = RichiestaView(interaction.user, membro, accetta)
        await interaction.response.send_message(
            await testo_per(interaction, "soc_sposi_richiesta", mittente=interaction.user.mention, destinatario=membro.mention, costo=COSTO_MATRIMONIO, pubblica=True),
            view=view, allowed_mentions=discord.AllowedMentions(users=[membro]),
        )

    @comando_di_gruppo("level", nome="mantieni", descrizione="Mantieni vivo il tuo matrimonio (vale 14 giorni).", sottogruppo=SG_SOCIALE)
    async def mantieni(self, interaction: discord.Interaction) -> None:
        if await _comando_rifiutato(interaction):
            return
        fatto = await sociale_repo.mantieni(interaction.guild.id, interaction.user.id)
        coniuge = await sociale_repo.coniuge(interaction.guild.id, interaction.user.id) if fatto else None
        testo = await testo_per(interaction, "soc_mantenuto" if fatto else "soc_non_sposato")
        await interaction.response.send_message(testo + (f" <@{coniuge}>" if coniuge else ""), ephemeral=True, allowed_mentions=NESSUNA_MENZIONE)

    @comando_di_gruppo("level", nome="divorzia", descrizione="Chiudi il tuo matrimonio.", sottogruppo=SG_SOCIALE)
    async def divorzia(self, interaction: discord.Interaction) -> None:
        if await _comando_rifiutato(interaction):
            return
        fatto = await sociale_repo.divorzia(interaction.guild.id, interaction.user.id)
        await interaction.response.send_message(await testo_per(interaction, "soc_divorzio" if fatto else "soc_non_sposato"), ephemeral=True)

    # ---------------------------------------------------------------- dati e prestigio
    @comando_di_gruppo("level", nome="azzera-dati", descrizione="Cancella i tuoi dati di gioco in questo server (monete, animali, pesci...).", sottogruppo=SG_SOCIALE)
    @app_commands.describe(conferma=f"Scrivi {PAROLA_AZZERA} per confermare")
    async def azzera_dati(self, interaction: discord.Interaction, conferma: app_commands.Range[str, 1, 20]) -> None:
        if await _comando_rifiutato(interaction):
            return
        if conferma.strip() != PAROLA_AZZERA:
            await interaction.response.send_message(await testo_per(interaction, "soc_azzera_parola", parola=PAROLA_AZZERA), ephemeral=True)
            return
        n = await sociale_repo.azzera_miei_dati(interaction.guild.id, interaction.user.id)
        logger.info("Dati di gioco azzerati dall'utente: server %s, utente %s, %s righe.", interaction.guild.id, interaction.user.id, n)
        await interaction.response.send_message(await testo_per(interaction, "soc_azzerati", righe=n), ephemeral=True)

    @comando_di_gruppo("monete", nome="prestigio", descrizione=f"Ricomincia da capo per un bonus permanente (+{BONUS_PRESTIGIO}% a lavoro e premio per livello).", sottogruppo=_SG_CONTO)
    @app_commands.describe(conferma=f"Scrivi {PAROLA_AZZERA} per confermare; senza conferma vedi cosa serve")
    async def prestigio(self, interaction: discord.Interaction, conferma: app_commands.Range[str, 1, 20] | None = None) -> None:
        if await _comando_rifiutato(interaction):
            return
        g, u = interaction.guild.id, interaction.user.id
        moneta = (await leveling_settings_repo.get_config(g)).impostazioni.currency_name
        if conferma is None or conferma.strip() != PAROLA_AZZERA:
            livello = await sociale_repo.livello_prestigio(g, u)
            from core.repositories.sociale_repo import soglia_prestigio

            await interaction.response.send_message(
                await testo_per(interaction, "soc_prestigio_info", livello=livello, soglia=soglia_prestigio(livello) or 0, moneta=moneta, bonus=BONUS_PRESTIGIO * livello, parola=PAROLA_AZZERA),
                ephemeral=True,
            )
            return
        esito, valore = await sociale_repo.prestigio(g, u)
        await interaction.response.send_message(
            await testo_per(interaction, f"soc_prestigio_{esito}", valore=valore, soglia=valore, moneta=moneta, bonus=BONUS_PRESTIGIO * valore),
            ephemeral=esito != "ok",
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(SocialeCog(bot))
