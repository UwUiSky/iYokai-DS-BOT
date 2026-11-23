"""
cogs/security/rete_protezione.py
================================
Rete di protezione tra server (VER-025, D111, D112): impostazioni del server (`/admin-sicurezza rete impostazioni`,
`rete ban`, `rete timeout-togli`), blocco dei server scorretti per il proprietario del bot (`/owner rete`), tasti che
restano validi dopo un riavvio e ascolto dei casi di moderazione gravi. Il lavoro con Discord sta in
core/rete_protezione.py, le regole in core/rete_protezione_logic.py.
Funzioni coperte: SPEC §6.22 (VER-025)
"""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from core import caso_eventi
from core import rete_protezione as rete
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.config import config
from core.i18n import testo_per
from core.rete_protezione_vista import BottoneRete, puo_togliere_timeout
from core.repositories.rete_repo import rete_repo

logger = logging.getLogger("iyokai.rete")

SOTTOGRUPPO = ("rete", "Rete di protezione tra server: avvisi, timeout, ban.")
MODI = [app_commands.Choice(name="Solo proposta con tasto", value="proposta"), app_commands.Choice(name="Ban automatico", value="automatico")]
AZIONI_OWNER = [
    app_commands.Choice(name="Blocca un server", value="blocca"),
    app_commands.Choice(name="Sblocca un server", value="sblocca"),
    app_commands.Choice(name="Elenca i bloccati", value="elenca"),
]


class ReteProtezioneCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._ascoltatore = rete.ascoltatore_casi(bot)

    async def cog_load(self) -> None:
        await super().cog_load()
        self.bot.add_dynamic_items(BottoneRete)
        caso_eventi.registra(self._ascoltatore)

    async def cog_unload(self) -> None:
        caso_eventi.rimuovi(self._ascoltatore)
        self.bot.remove_dynamic_items(BottoneRete)
        await super().cog_unload()

    # ------------------------------------------------------------------ impostazioni del server
    @comando_di_gruppo(
        "admin-sicurezza", nome="impostazioni", descrizione="Rete di protezione: avvisi dagli altri server e timeout di sicurezza.",
        sottogruppo=SOTTOGRUPPO,
    )
    @app_commands.describe(
        ricezione="Ricevere gli avvisi sugli utenti sanzionati in altri server (di base sì)",
        canale="Canale dove arrivano gli avvisi (senza: messaggio privato al proprietario)",
        togli_canale="Torna al messaggio privato al proprietario",
        mostra_origine="Far vedere il nome di questo server negli avvisi che partono da qui (di base no)",
        timeout_ore="Ore di timeout per un account compromesso (da 1 a 672, di base 24)",
    )
    async def impostazioni(
        self,
        interaction: discord.Interaction,
        ricezione: bool | None = None,
        canale: discord.TextChannel | None = None,
        togli_canale: bool | None = None,
        mostra_origine: bool | None = None,
        timeout_ore: app_commands.Range[int, 1, 672] | None = None,
    ) -> None:
        guild = interaction.guild
        cambi: dict = {}
        if ricezione is not None:
            cambi["ricezione"] = ricezione
        if canale is not None:
            permessi = canale.permissions_for(guild.me)
            if not (permessi.send_messages and permessi.embed_links):
                return await interaction.response.send_message(await testo_per(interaction, "rete_ban_fallito"), ephemeral=True)
            cambi["canale_id"] = canale.id
        elif togli_canale:
            cambi["canale_id"] = None
        if mostra_origine is not None:
            cambi["mostra_origine"] = mostra_origine
        if timeout_ore is not None:
            cambi["timeout_ore"] = int(timeout_ore)
        if cambi:
            await rete_repo.imposta(guild.id, **cambi)
        await interaction.response.send_message(
            await self._riepilogo(interaction, saved=bool(cambi)), ephemeral=True, allowed_mentions=discord.AllowedMentions.none()
        )

    async def _riepilogo(self, interaction: discord.Interaction, *, saved: bool) -> str:
        i = await rete_repo.impostazioni(interaction.guild.id)
        sino = lambda v: "rete_si" if v else "rete_no"  # noqa: E731
        testo = await testo_per(
            interaction, "rete_impostazioni_stato",
            ricezione=await testo_per(interaction, sino(i.ricezione)),
            canale=f"<#{i.canale_id}>" if i.canale_id else await testo_per(interaction, "rete_canale_proprietario"),
            origine=await testo_per(interaction, sino(i.mostra_origine)), ore=i.timeout_ore,
            ban=await testo_per(interaction, sino(i.ban_aderisce)), modo=await testo_per(interaction, f"rete_modo_{i.ban_modo}"),
        )
        return ((await testo_per(interaction, "rete_impostazioni_salvate")) + "\n" if saved else "") + testo

    @comando_di_gruppo(
        "admin-sicurezza", nome="ban", descrizione="Rete facoltativa dei ban: aderisci, scegli proposta o automatico, annulla.",
        sottogruppo=SOTTOGRUPPO,
    )
    @app_commands.describe(
        aderisce="Entrare (sì) o uscire (no) dalla rete dei ban",
        modo="Cosa fare quando un server aderente banna per un motivo grave",
        annulla="Toglie il ban messo dalla rete a questo utente",
    )
    @app_commands.choices(modo=MODI)
    async def ban_rete(
        self,
        interaction: discord.Interaction,
        aderisce: bool | None = None,
        modo: app_commands.Choice[str] | None = None,
        annulla: discord.User | None = None,
    ) -> None:
        guild = interaction.guild
        if annulla is not None:
            proposta = await rete_repo.ultima_applicata(annulla.id, guild.id)
            fatto = proposta is not None and await rete.annulla_ban(self.bot, guild, proposta["id"], interaction.user.id)
            chiave = "rete_ban_annulla_fatto" if fatto else "rete_ban_annulla_niente"
            return await interaction.response.send_message(
                await testo_per(interaction, chiave, utente=f"<@{annulla.id}>"), ephemeral=True, allowed_mentions=discord.AllowedMentions.none()
            )
        cambi: dict = {}
        if aderisce is not None:
            cambi["ban_aderisce"] = aderisce
        if modo is not None:
            cambi["ban_modo"] = modo.value
        if cambi:
            await rete_repo.imposta(guild.id, **cambi)
        i = await rete_repo.impostazioni(guild.id)
        if aderisce is True:
            testo = await testo_per(interaction, "rete_ban_aderito", modo=await testo_per(interaction, f"rete_modo_{i.ban_modo}"))
        elif aderisce is False:
            testo = await testo_per(interaction, "rete_ban_lasciata")
        else:
            testo = await self._riepilogo(interaction, saved=bool(cambi))
        await interaction.response.send_message(testo, ephemeral=True, allowed_mentions=discord.AllowedMentions.none())

    @comando_di_gruppo(
        "admin-sicurezza", nome="timeout-togli", descrizione="Toglie il timeout messo dalla rete per un account compromesso.",
        sottogruppo=SOTTOGRUPPO,
    )
    @app_commands.describe(utente="L'utente a cui togliere il timeout")
    async def timeout_togli(self, interaction: discord.Interaction, utente: discord.User) -> None:
        if not puo_togliere_timeout(interaction.guild, interaction.user.id):  # solo proprietario del server o del bot
            return await interaction.response.send_message(await testo_per(interaction, "rete_non_permesso"), ephemeral=True)
        fatto = await rete.togli_timeout(self.bot, interaction.guild, utente.id, interaction.user.id)
        chiave = "rete_timeout_tolto" if fatto else "rete_timeout_non_c_e"
        await interaction.response.send_message(
            await testo_per(interaction, chiave, utente=f"<@{utente.id}>"), ephemeral=True, allowed_mentions=discord.AllowedMentions.none()
        )

    # ------------------------------------------------------------------ proprietario del bot
    @comando_di_gruppo(
        "owner", nome="rete", descrizione="Solo proprietario del bot: blocca i server che segnalano in modo scorretto.",
    )
    @app_commands.describe(azione="Cosa fare", server_id="ID del server (per blocca e sblocca)", motivo="Perché (per blocca)")
    @app_commands.choices(azione=AZIONI_OWNER)
    async def rete_owner(
        self,
        interaction: discord.Interaction,
        azione: app_commands.Choice[str],
        server_id: app_commands.Range[str, 5, 20] | None = None,
        motivo: app_commands.Range[str, 0, 200] | None = None,
    ) -> None:
        if interaction.user.id != config.OWNER_ID:
            return await interaction.response.send_message(await testo_per(interaction, "rete_owner_solo_proprietario"), ephemeral=True)
        if azione.value == "elenca":
            righe = [f"`{r['guild_id']}` {discord.utils.escape_markdown((r['motivo'] or '')[:100])}" for r in await rete_repo.elenco_bloccati(25)]
            return await interaction.response.send_message("\n".join(righe) or await testo_per(interaction, "rete_owner_elenco_vuoto"), ephemeral=True)
        if not server_id or not server_id.isdigit():
            return await interaction.response.send_message(await testo_per(interaction, "rete_owner_id_non_valido"), ephemeral=True)
        gid = int(server_id)
        if azione.value == "blocca":
            await rete_repo.blocca(gid, interaction.user.id, motivo)
            chiave = "rete_owner_bloccato"
        else:
            chiave = "rete_owner_sbloccato" if await rete_repo.sblocca(gid) else "rete_owner_non_bloccato"
        await interaction.response.send_message(await testo_per(interaction, chiave, server=gid), ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ReteProtezioneCog(bot))
