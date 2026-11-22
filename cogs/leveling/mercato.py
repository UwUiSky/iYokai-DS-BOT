"""
cogs/leveling/mercato.py
========================
Mercato tra utenti (/mercato vendi, elenco, compra, offri, accetta, ritira) e fondo premi del server
(/mercato dona, fondo). Tutta la logica sta in core/repositories/mercato_repo.py (transazioni con righe bloccate in ordine).
Funzioni coperte: ECO-074, ECO-120
"""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands, tasks

from cogs.leveling.leveling import _comando_rifiutato
from core.command_groups import CogConGruppi, comando_di_gruppo, togli_comandi_del_cog
from core.i18n import testo_per
from core.repositories.leveling_settings_repo import leveling_settings_repo
from core.repositories.mercato_repo import GIORNI_DI_BASE, GIORNI_MASSIMI, Esito, mercato_repo

logger = logging.getLogger("iyokai.mercato")
NESSUNA_MENZIONE = discord.AllowedMentions.none()
ID = app_commands.Range[int, 1, 2_147_483_647]
ANN = app_commands.Range[int, 1, 9_000_000_000_000_000]


class MercatoCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._scadenze.start()

    def cog_unload(self) -> None:
        self._scadenze.cancel()
        togli_comandi_del_cog(self)

    @tasks.loop(minutes=10)
    async def _scadenze(self) -> None:
        try:
            await mercato_repo.scadenze()
        except Exception:
            logger.exception("Scadenza degli annunci")

    @_scadenze.before_loop
    async def _prima(self) -> None:
        await self.bot.wait_until_ready()

    @staticmethod
    async def _dillo(interaction: discord.Interaction, esito: Esito, ok: str = "mer_fatto", **kw) -> None:
        chiave = ok if esito is Esito.FATTO else f"mer_{esito.value}"
        await interaction.response.send_message(await testo_per(interaction, chiave, **kw), ephemeral=True)

    @comando_di_gruppo("mercato", nome="vendi", descrizione="Metti un tuo oggetto in vendita agli altri membri.")
    @app_commands.describe(oggetto="ID dell'oggetto (vedi /monete inventario)", prezzo="Prezzo in monete", quantita="Quanti pezzi", giorni=f"Durata (1-{GIORNI_MASSIMI})")
    async def vendi(
        self, interaction: discord.Interaction, oggetto: ID, prezzo: app_commands.Range[int, 1, 100_000_000],
        quantita: app_commands.Range[int, 1, 100] = 1, giorni: app_commands.Range[int, 1, GIORNI_MASSIMI] = GIORNI_DI_BASE,
    ) -> None:
        if await _comando_rifiutato(interaction):
            return
        esito = await mercato_repo.pubblica(interaction.guild.id, interaction.user.id, oggetto, quantita, prezzo, giorni)
        await self._dillo(interaction, esito, "mer_pubblicato")

    @comando_di_gruppo("mercato", nome="elenco", descrizione="Gli annunci del mercato (anche solo di un membro).")
    @app_commands.describe(pagina="Pagina", venditore="Solo gli annunci di questo membro")
    async def elenco(self, interaction: discord.Interaction, pagina: app_commands.Range[int, 1, 100] = 1, venditore: discord.Member | None = None) -> None:
        if await _comando_rifiutato(interaction):
            return
        g = interaction.guild.id
        moneta = (await leveling_settings_repo.get_config(g)).impostazioni.currency_name
        annunci = await mercato_repo.elenco(g, pagina - 1, 10, venditore.id if venditore else None)
        if not annunci:
            await interaction.response.send_message(await testo_per(interaction, "mer_vuoto"), ephemeral=True)
            return
        righe = [
            f"`{a.id}` {a.quantita}× **{a.nome[:40]}** — {a.prezzo} {moneta} · <@{a.venditore}> · <t:{int(a.scade_at.timestamp())}:R>"
            + (f" · {a.offerte}✋" if a.offerte else "") for a in annunci
        ]
        await interaction.response.send_message("\n".join(righe)[:1900], ephemeral=True, allowed_mentions=NESSUNA_MENZIONE)

    @comando_di_gruppo("mercato", nome="compra", descrizione="Compra un annuncio al prezzo indicato.")
    @app_commands.describe(annuncio="Numero dell'annuncio")
    async def compra(self, interaction: discord.Interaction, annuncio: ANN) -> None:
        if await _comando_rifiutato(interaction):
            return
        await self._dillo(interaction, await mercato_repo.compra(interaction.guild.id, interaction.user.id, annuncio), "mer_comprato")

    @comando_di_gruppo("mercato", nome="offri", descrizione="Fai un'offerta più bassa: le monete restano in custodia finché non risponde.")
    @app_commands.describe(annuncio="Numero dell'annuncio", importo="Monete offerte (meno del prezzo)")
    async def offri(self, interaction: discord.Interaction, annuncio: ANN, importo: app_commands.Range[int, 1, 100_000_000]) -> None:
        if await _comando_rifiutato(interaction):
            return
        await self._dillo(interaction, await mercato_repo.offri(interaction.guild.id, interaction.user.id, annuncio, importo), "mer_offerto")

    @comando_di_gruppo("mercato", nome="accetta", descrizione="Accetta l'offerta di un membro sul tuo annuncio (senza membro: vedi le offerte).")
    @app_commands.describe(annuncio="Numero del tuo annuncio", offerente="Chi ha fatto l'offerta")
    async def accetta(self, interaction: discord.Interaction, annuncio: ANN, offerente: discord.Member | None = None) -> None:
        if await _comando_rifiutato(interaction):
            return
        g = interaction.guild.id
        if offerente is None:
            offerte = await mercato_repo.offerte_di(g, annuncio)
            testo = "\n".join(f"<@{u}>: {i}" for u, i in offerte) or await testo_per(interaction, "mer_nessuna_offerta")
            await interaction.response.send_message(testo[:1900], ephemeral=True, allowed_mentions=NESSUNA_MENZIONE)
            return
        await self._dillo(interaction, await mercato_repo.accetta(g, interaction.user.id, annuncio, offerente.id), "mer_accettato")

    @comando_di_gruppo("mercato", nome="ritira", descrizione="Ritira un tuo annuncio (o una tua offerta): oggetto e monete tornano a chi spettano.")
    @app_commands.describe(annuncio="Numero dell'annuncio", offerta="Sì = ritiri la tua offerta, no = il tuo annuncio")
    async def ritira(self, interaction: discord.Interaction, annuncio: ANN, offerta: bool = False) -> None:
        if await _comando_rifiutato(interaction):
            return
        g, u = interaction.guild.id, interaction.user.id
        esito = await (mercato_repo.ritira_offerta(g, u, annuncio) if offerta else mercato_repo.ritira(g, u, annuncio))
        await self._dillo(interaction, esito, "mer_ritirato")

    @comando_di_gruppo("mercato", nome="dona", descrizione="Dona monete o un oggetto al fondo premi del server.")
    @app_commands.describe(monete="Monete da donare alla cassa", oggetto="ID di un oggetto da donare al fondo")
    async def dona(self, interaction: discord.Interaction, monete: app_commands.Range[int, 1, 10_000_000] | None = None, oggetto: ID | None = None) -> None:
        if await _comando_rifiutato(interaction):
            return
        if (monete is None) == (oggetto is None):
            await interaction.response.send_message(await testo_per(interaction, "mer_dona_scelta"), ephemeral=True)
            return
        g, u = interaction.guild.id, interaction.user.id
        if monete is not None:
            esito = Esito.FATTO if await mercato_repo.dona_monete(g, u, monete) else Esito.POCHE_MONETE
        else:
            esito = await mercato_repo.dona_oggetto(g, u, oggetto)
        await self._dillo(interaction, esito, "mer_donato")

    @comando_di_gruppo("mercato", nome="fondo", descrizione="Gli oggetti donati al fondo premi del server.")
    async def fondo(self, interaction: discord.Interaction) -> None:
        if await _comando_rifiutato(interaction):
            return
        voci = await mercato_repo.fondo(interaction.guild.id)
        testo = "\n".join(f"`{i}` {q}× {n[:40]}" for i, n, q in voci) or await testo_per(interaction, "mer_vuoto")
        await interaction.response.send_message(testo[:1900], ephemeral=True, allowed_mentions=NESSUNA_MENZIONE)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(MercatoCog(bot))
