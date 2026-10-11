"""
cogs/moderation/ban_appeal.py
=============================
Appello contro i ban manuali (ban e tempban). Se il server ha scelto un
canale per gli appelli (`/modban appelli canale`), il messaggio privato
mandato PRIMA del ban porta il bottone «Fai appello»: l'utente scrive il
testo in un modulo (un appello ogni 24 ore), lo staff lo trova nel canale
con i bottoni Accetta e Rifiuta. Accettare toglie il ban e avvisa l'utente.
Solo chi può bannare decide. I bottoni sono persistenti (DynamicItem).
Funzioni coperte: SPEC §23 (NF-30, issue #101)
Dipende da: core/ban_appeal_logic.py
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from core.ban_appeal_logic import (
    CASI_CON_APPELLO,
    MAX_TESTO_APPELLO,
    MIN_TESTO_APPELLO,
    STATO_ACCETTATO,
    STATO_APERTO,
    STATO_RIFIUTATO,
    attesa_rimasta,
    attesa_a_parole,
    lunghezza_valida,
)
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.database import db
from core.ui_base import BaseModal, BaseView
from core.repositories.moderation_repo import moderation_repo
from cogs.moderation._shared import MODULE_ACTIONS, ensure_module_enabled, post_to_mod_log, truncate_text

logger = logging.getLogger("iyokai.moderation.ban_appeal")

SETTING_CANALE_APPELLI = "appelli_channel_id"


async def vista_appello(guild_id: int) -> BaseView | None:
    """Il bottone da mettere nel DM del ban; None se il server non ha il canale appelli."""
    if await db.get_guild_setting(guild_id, SETTING_CANALE_APPELLI) is None:
        return None
    vista = BaseView(timeout=None)
    vista.add_item(BottoneApriAppello(guild_id))
    return vista


class ModuloAppello(BaseModal, title="Appello contro il ban"):
    testo = discord.ui.TextInput(
        label="Perché dovremmo togliere il ban?",
        style=discord.TextStyle.paragraph,
        min_length=MIN_TESTO_APPELLO,
        max_length=MAX_TESTO_APPELLO,
    )

    def __init__(self, guild_id: int) -> None:
        super().__init__()
        self.guild_id = guild_id

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        esito = await invia_appello(interaction.client, self.guild_id, interaction.user, str(self.testo))
        await interaction.followup.send(esito, ephemeral=True)


async def invia_appello(
    bot: discord.Client, guild_id: int, utente: discord.abc.User, testo: str, adesso: datetime | None = None
) -> str:
    """Registra l'appello e lo manda allo staff. Restituisce il messaggio per l'utente."""
    adesso = adesso or datetime.now(timezone.utc)
    if not lunghezza_valida(testo):
        return "Il testo deve avere tra 10 e 1500 caratteri."
    guild = bot.get_guild(guild_id)
    canale_id = await db.get_guild_setting(guild_id, SETTING_CANALE_APPELLI)
    canale = guild.get_channel(canale_id) if guild and canale_id else None
    if canale is None:
        return "Questo server non accetta appelli in questo momento."
    caso = None
    for tipo in CASI_CON_APPELLO:
        caso = await moderation_repo.get_latest_active_case(guild_id, utente.id, tipo)
        if caso is not None:
            break
    if caso is None:
        return "Non risulta nessun ban attivo a tuo nome in questo server."
    mancano = attesa_rimasta(await moderation_repo.last_appeal_time(guild_id, utente.id), adesso)
    if mancano is not None:
        return f"Hai già fatto appello. Puoi riprovare tra {attesa_a_parole(mancano)}."

    appello_id = await moderation_repo.create_appeal(guild_id, utente.id, caso.case_number, testo.strip())
    embed = discord.Embed(
        title=f"Appello #{appello_id} — caso #{caso.case_number}",
        description=truncate_text(testo.strip(), 3500),
        color=discord.Color.orange(),
    )
    embed.add_field(name="Utente", value=f"<@{utente.id}> ({utente.id})", inline=False)
    embed.add_field(name="Motivo del ban", value=truncate_text(caso.reason or "Nessun motivo", 1000), inline=False)
    vista = BaseView(timeout=None)
    vista.add_item(BottoneEsitoAppello(appello_id, True))
    vista.add_item(BottoneEsitoAppello(appello_id, False))
    try:
        await canale.send(embed=embed, view=vista)
    except discord.HTTPException:
        return "Non sono riuscito a consegnare l'appello allo staff: riprova più tardi."
    return "Appello inviato. Lo staff lo leggerà e riceverai una risposta qui."


class BottoneApriAppello(
    discord.ui.DynamicItem[discord.ui.Button], template=r"appello:apri:(?P<g>[0-9]+)"
):
    def __init__(self, guild_id: int) -> None:
        super().__init__(
            discord.ui.Button(
                label="Fai appello", style=discord.ButtonStyle.primary, custom_id=f"appello:apri:{guild_id}"
            )
        )
        self.guild_id = guild_id

    @classmethod
    async def from_custom_id(cls, interaction, item, match):
        return cls(int(match["g"]))

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(ModuloAppello(self.guild_id))


class BottoneEsitoAppello(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"appello:esito:(?P<id>[0-9]+):(?P<s>si|no)",
):
    def __init__(self, appello_id: int, accetta: bool) -> None:
        super().__init__(
            discord.ui.Button(
                label="Accetta" if accetta else "Rifiuta",
                style=discord.ButtonStyle.success if accetta else discord.ButtonStyle.danger,
                custom_id=f"appello:esito:{appello_id}:{'si' if accetta else 'no'}",
            )
        )
        self.appello_id = appello_id
        self.accetta = accetta

    @classmethod
    async def from_custom_id(cls, interaction, item, match):
        return cls(int(match["id"]), match["s"] == "si")

    async def callback(self, interaction: discord.Interaction) -> None:
        await decidi_appello(interaction, self.appello_id, self.accetta)


async def decidi_appello(interaction: discord.Interaction, appello_id: int, accetta: bool) -> None:
    """Lo staff decide: solo chi può bannare; due click insieme valgono uno."""
    guild = interaction.guild
    if guild is None or not interaction.user.guild_permissions.ban_members:
        await interaction.response.send_message(
            "Solo chi può bannare i membri decide sugli appelli.", ephemeral=True
        )
        return
    appello = await moderation_repo.get_appeal(appello_id)
    if appello is None or appello["guild_id"] != guild.id:
        await interaction.response.send_message("Appello non trovato.", ephemeral=True)
        return
    stato = STATO_ACCETTATO if accetta else STATO_RIFIUTATO
    if not await moderation_repo.decide_appeal(appello_id, stato, interaction.user.id):
        await interaction.response.send_message("Questo appello è già stato deciso.", ephemeral=True)
        return
    await interaction.response.defer()
    uid = appello["user_id"]
    avviso = ""
    if accetta:
        try:
            await guild.unban(discord.Object(id=uid), reason=f"Appello #{appello_id} accettato")
        except discord.NotFound:
            pass
        except discord.HTTPException:
            avviso = " Attenzione: il ban non è stato tolto, usa /modban unban."
        for tipo in CASI_CON_APPELLO:
            await moderation_repo.revoke_active_cases_for_user(guild.id, uid, tipo, interaction.user.id)
    messaggio = (
        f"Il tuo appello su **{guild.name}** è stato accettato."
        if accetta
        else f"Il tuo appello su **{guild.name}** è stato rifiutato."
    )
    try:
        utente = await interaction.client.fetch_user(uid)
        await utente.send(messaggio)
    except discord.HTTPException:
        avviso += " (Non sono riuscito a scrivere all'utente.)"
    embed = interaction.message.embeds[0] if interaction.message and interaction.message.embeds else discord.Embed()
    embed.color = discord.Color.green() if accetta else discord.Color.red()
    embed.set_footer(text=f"{'Accettato' if accetta else 'Rifiutato'} da {interaction.user.display_name}")
    await interaction.edit_original_response(embed=embed, view=None)
    log = discord.Embed(
        title=f"Appello #{appello_id} {stato}", color=embed.color,
    )
    log.add_field(name="Utente", value=f"<@{uid}>", inline=True)
    log.add_field(name="Moderatore", value=interaction.user.mention, inline=True)
    await post_to_mod_log(guild, log)
    if avviso:
        await interaction.followup.send(avviso.strip(), ephemeral=True)


class ModerationBanAppealCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @comando_di_gruppo(
        "modban",
        nome="canale",
        descrizione="Sceglie il canale staff per gli appelli (vuoto per spegnerli).",
        sottogruppo=("appelli", "Appelli contro i ban."),
    )
    @app_commands.describe(channel="Il canale dove arrivano gli appelli; vuoto = appelli spenti")
    async def canale(
        self, interaction: discord.Interaction, channel: discord.TextChannel | None = None
    ) -> None:
        if not await ensure_module_enabled(interaction, MODULE_ACTIONS):
            return
        await db.set_guild_setting(
            interaction.guild.id, SETTING_CANALE_APPELLI, channel.id if channel else None,
            changed_by=interaction.user.id,
        )
        testo = (
            f"Gli appelli arriveranno in {channel.mention}. Il bottone compare nel messaggio privato dei prossimi ban."
            if channel
            else "Appelli spenti."
        )
        await interaction.response.send_message(testo, ephemeral=True)

    @comando_di_gruppo(
        "modban",
        nome="elenco",
        descrizione="Mostra gli ultimi appelli del server.",
        sottogruppo=("appelli", "Appelli contro i ban."),
    )
    @app_commands.describe(stato="Solo gli appelli in questo stato")
    @app_commands.choices(
        stato=[
            app_commands.Choice(name="Aperti", value=STATO_APERTO),
            app_commands.Choice(name="Accettati", value=STATO_ACCETTATO),
            app_commands.Choice(name="Rifiutati", value=STATO_RIFIUTATO),
        ]
    )
    async def elenco(
        self, interaction: discord.Interaction, stato: app_commands.Choice[str] | None = None
    ) -> None:
        if not await ensure_module_enabled(interaction, MODULE_ACTIONS):
            return
        appelli = await moderation_repo.list_appeals(interaction.guild.id, stato.value if stato else None)
        if not appelli:
            await interaction.response.send_message("Nessun appello.", ephemeral=True)
            return
        righe = [
            f"**#{a['id']}** — <@{a['user_id']}> — {a['stato']} — caso #{a['case_number']}" for a in appelli
        ]
        embed = discord.Embed(title="Appelli", description="\n".join(righe)[:4000], color=discord.Color.blurple())
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    bot.add_dynamic_items(BottoneApriAppello, BottoneEsitoAppello)
    await bot.add_cog(ModerationBanAppealCog(bot))
