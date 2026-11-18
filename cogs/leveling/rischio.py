"""
cogs/leveling/rischio.py
========================
Banca e lavoro (/monete conto banca, lavoro, dimettiti) e guadagni a rischio o con pausa
(/monete rischio colpo, avventura, furto, elemosina, cerca). Il furto è spento di base e colpisce solo i
contanti. Ogni azione è una transazione sola (core/repositories/rischio_repo.py).
Funzioni coperte: ECO-004, ECO-029, ECO-030, ECO-031, ECO-032, ECO-040, ECO-041
Dipende da: core/rischio_logic.py
"""

from __future__ import annotations

import logging
import random

import discord
from discord import app_commands
from discord.ext import commands

from cogs.leveling.leveling import _comando_rifiutato, _format_seconds
from core.command_groups import CogConGruppi, comando_di_gruppo, togli_comandi_del_cog
from core.i18n import testo_per
from core.repositories.leveling_settings_repo import leveling_settings_repo
from core.repositories.rischio_repo import EsitoFurto, rischio_repo
from core.rischio_logic import (
    LAVORI, LUOGHI, PAUSA_CERCA, PAUSA_COLPO, PAUSA_ELEMOSINA, PAUSA_FURTO, cerca, elemosina, gioca_colpo,
    lavoro_per_turni, turni_alla_promozione,
)

logger = logging.getLogger("iyokai.leveling.rischio")
NESSUNA_MENZIONE = discord.AllowedMentions.none()
RNG = random.SystemRandom()
_SG_RISCHIO = ("rischio", "Colpi, furti e piccoli guadagni")
_SG_CONTO = ("conto", "Banca e lavoro")
PAUSA_AVVENTURA = 3600
SUCCESSO_AVVENTURA = 55
_SCELTE_BANCA = [
    app_commands.Choice(name="Vedi", value="vedi"),
    app_commands.Choice(name="Deposita", value="deposita"),
    app_commands.Choice(name="Preleva", value="preleva"),
]
_SCELTE_LUOGO = [app_commands.Choice(name=n.capitalize(), value=n) for n in LUOGHI]


class RischioCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    def cog_unload(self) -> None:
        togli_comandi_del_cog(self)

    async def _impostazioni(self, interaction: discord.Interaction):
        return (await leveling_settings_repo.get_config(interaction.guild.id)).impostazioni

    async def _pausa_attiva(self, interaction: discord.Interaction, chiave: str, pausa_s: int) -> None:
        resto = await rischio_repo.pausa_rimasta(interaction.guild.id, interaction.user.id, chiave, pausa_s)
        await interaction.response.send_message(
            await testo_per(interaction, "rsk_pausa", tempo=_format_seconds(max(1, resto))), ephemeral=True
        )

    # ---------------------------------------------------------------- banca e lavoro
    @comando_di_gruppo("monete", nome="banca", descrizione="La tua banca: vedi, deposita o preleva (i furti toccano solo i contanti).", sottogruppo=_SG_CONTO)
    @app_commands.describe(azione="Cosa fare", importo="Quante monete (non serve per «Vedi»)")
    @app_commands.choices(azione=_SCELTE_BANCA)
    async def banca(
        self,
        interaction: discord.Interaction,
        azione: app_commands.Choice[str],
        importo: app_commands.Range[int, 1, 1_000_000_000] | None = None,
    ) -> None:
        if await _comando_rifiutato(interaction):
            return
        g, u = interaction.guild.id, interaction.user.id
        if azione.value != "vedi":
            if importo is None:
                await interaction.response.send_message(await testo_per(interaction, "rsk_serve_importo"), ephemeral=True)
                return
            if azione.value == "deposita":
                nuovo = await rischio_repo.deposita(g, u, importo)
            else:
                nuovo = await rischio_repo.preleva(g, u, importo)
            if nuovo is None:
                await interaction.response.send_message(await testo_per(interaction, "rsk_banca_no"), ephemeral=True)
                return
        else:
            nuovo = await rischio_repo.banca(g, u)
        moneta = (await self._impostazioni(interaction)).currency_name
        await interaction.response.send_message(
            await testo_per(interaction, "rsk_banca", contanti=nuovo.contanti, banca=nuovo.banca, moneta=moneta), ephemeral=True
        )

    @comando_di_gruppo("monete", nome="lavoro", descrizione="Il tuo lavoro attuale e quanto manca alla promozione.", sottogruppo=_SG_CONTO)
    async def lavoro(self, interaction: discord.Interaction) -> None:
        if await _comando_rifiutato(interaction):
            return
        turni = await rischio_repo.turni(interaction.guild.id, interaction.user.id)
        nome, _, molt = lavoro_per_turni(turni)
        mancano = turni_alla_promozione(turni)
        chiave = "rsk_lavoro_max" if mancano is None else "rsk_lavoro"
        await interaction.response.send_message(
            await testo_per(interaction, chiave, nome=nome, turni=turni, molt=molt, mancano=mancano or 0), ephemeral=True
        )

    @comando_di_gruppo("monete", nome="dimettiti", descrizione="Lascia il lavoro e ricomincia da stagista.", sottogruppo=_SG_CONTO)
    async def dimettiti(self, interaction: discord.Interaction) -> None:
        if await _comando_rifiutato(interaction):
            return
        persi = await rischio_repo.dimettiti(interaction.guild.id, interaction.user.id)
        await interaction.response.send_message(await testo_per(interaction, "rsk_dimesso", turni=persi), ephemeral=True)

    # ---------------------------------------------------------------- colpo e avventura
    async def _colpo(self, interaction, chiave, pausa_s, successo, molt) -> None:
        if await _comando_rifiutato(interaction):
            return
        g, u = interaction.guild.id, interaction.user.id
        i = await self._impostazioni(interaction)
        if successo is None:
            successo = i.colpo_successo
        contanti = (await rischio_repo.banca(g, u)).contanti
        esito = gioca_colpo(RNG, successo, i.work_min, i.work_max, contanti, molt)
        # La multa può essere 0 (niente contanti): si consuma comunque la pausa con un importo minimo valido.
        r = await rischio_repo.colpo(g, u, chiave, pausa_s, esito.riuscito, max(1, esito.importo))
        if r is None:
            await self._pausa_attiva(interaction, chiave, pausa_s)
            return
        variazione, saldo = r
        testo = await testo_per(
            interaction, "rsk_colpo_ok" if esito.riuscito else "rsk_colpo_ko",
            importo=abs(variazione), moneta=i.currency_name, saldo=saldo, pubblica=True,
        )
        await interaction.response.send_message(testo, allowed_mentions=NESSUNA_MENZIONE)

    @comando_di_gruppo("monete", nome="colpo", descrizione="Un colpo rischioso: paga alta se va bene, multa se va male.", sottogruppo=_SG_RISCHIO)
    async def colpo(self, interaction: discord.Interaction) -> None:
        await self._colpo(interaction, "colpo", PAUSA_COLPO, None, (2, 4))

    @comando_di_gruppo("monete", nome="avventura", descrizione="Un'uscita a rischio più prudente: paga meno, riesce più spesso.", sottogruppo=_SG_RISCHIO)
    async def avventura(self, interaction: discord.Interaction) -> None:
        await self._colpo(interaction, "avventura", PAUSA_AVVENTURA, SUCCESSO_AVVENTURA, (1, 2))

    # ---------------------------------------------------------------- furto
    @comando_di_gruppo("monete", nome="furto", descrizione="Prova a rubare dei contanti a un membro (solo se il server lo permette).", sottogruppo=_SG_RISCHIO)
    @app_commands.describe(membro="A chi")
    async def furto(self, interaction: discord.Interaction, membro: discord.Member) -> None:
        if await _comando_rifiutato(interaction):
            return
        i = await self._impostazioni(interaction)
        if not i.furto_attivo:
            await interaction.response.send_message(await testo_per(interaction, "rsk_furto_spento"), ephemeral=True)
            return
        if membro.id == interaction.user.id or membro.bot:
            await interaction.response.send_message(await testo_per(interaction, "rsk_furto_bersaglio"), ephemeral=True)
            return
        riuscito = RNG.randint(1, 100) <= i.furto_successo
        f = await rischio_repo.furto(interaction.guild.id, interaction.user.id, membro.id, riuscito, i.furto_percentuale, PAUSA_FURTO)
        if f.esito is EsitoFurto.PAUSA:
            await self._pausa_attiva(interaction, "furto", PAUSA_FURTO)
            return
        if f.esito in (EsitoFurto.POCHI_CONTANTI, EsitoFurto.PROTETTO):
            chiave = "rsk_furto_pochi" if f.esito is EsitoFurto.POCHI_CONTANTI else "rsk_furto_protetto"
            await interaction.response.send_message(await testo_per(interaction, chiave), ephemeral=True)
            return
        chiave = "rsk_furto_ok" if f.esito is EsitoFurto.RIUSCITO else "rsk_furto_ko"
        await interaction.response.send_message(
            await testo_per(interaction, chiave, importo=f.importo, moneta=i.currency_name, vittima=membro.display_name[:40], pubblica=True),
            allowed_mentions=NESSUNA_MENZIONE,
        )
        try:  # ECO-156: la vittima lo sa
            if f.esito is EsitoFurto.RIUSCITO:
                await membro.send(f"💸 In **{interaction.guild.name[:60]}** ti hanno rubato {f.importo} {i.currency_name}.")
        except (discord.HTTPException, AttributeError):
            pass

    # ---------------------------------------------------------------- elemosina e cerca
    @comando_di_gruppo("monete", nome="elemosina", descrizione="Chiedi l'elemosina: una piccola cifra, a volte niente.", sottogruppo=_SG_RISCHIO)
    async def elemosina(self, interaction: discord.Interaction) -> None:
        if await _comando_rifiutato(interaction):
            return
        dato = elemosina(RNG)
        saldo = await rischio_repo.guadagna(interaction.guild.id, interaction.user.id, "elemosina", PAUSA_ELEMOSINA, dato)
        if saldo is None:
            await self._pausa_attiva(interaction, "elemosina", PAUSA_ELEMOSINA)
            return
        moneta = (await self._impostazioni(interaction)).currency_name
        chiave = "rsk_elemosina_ok" if dato else "rsk_elemosina_no"
        await interaction.response.send_message(await testo_per(interaction, chiave, importo=dato, moneta=moneta, pubblica=True))

    @comando_di_gruppo("monete", nome="cerca", descrizione="Cerca monete in un luogo a scelta.", sottogruppo=_SG_RISCHIO)
    @app_commands.describe(luogo="Dove cercare")
    @app_commands.choices(luogo=_SCELTE_LUOGO)
    async def cerca(self, interaction: discord.Interaction, luogo: app_commands.Choice[str]) -> None:
        if await _comando_rifiutato(interaction):
            return
        dato = cerca(RNG, luogo.value)
        saldo = await rischio_repo.guadagna(interaction.guild.id, interaction.user.id, "cerca", PAUSA_CERCA, dato)
        if saldo is None:
            await self._pausa_attiva(interaction, "cerca", PAUSA_CERCA)
            return
        moneta = (await self._impostazioni(interaction)).currency_name
        chiave = "rsk_cerca_ok" if dato else "rsk_cerca_no"
        await interaction.response.send_message(
            await testo_per(interaction, chiave, importo=dato, moneta=moneta, luogo=luogo.value, pubblica=True)
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(RischioCog(bot))
