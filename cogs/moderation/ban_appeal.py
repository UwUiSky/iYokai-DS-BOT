"""
cogs/moderation/ban_appeal.py
=============================
Appello contro i ban manuali (ban e tempban). Se il server ha scelto un
canale per gli appelli (`/modban appelli canale`), il messaggio privato
mandato PRIMA del ban porta il bottone «Fai appello»: l'utente scrive il
testo in un modulo (un appello ogni 24 ore), lo staff lo trova nel canale
con i bottoni Accetta e Rifiuta. Accettare toglie il ban (prima di segnare «accettato», solo quello contestato)
e avvisa l'utente; se il ban non si toglie l'appello resta aperto.
Solo chi può bannare decide. I bottoni sono persistenti (DynamicItem).
Chi ha perso il messaggio (o aveva i DM chiusi) scrive al bot in privato:
come per lo spam-trap, riceve un bottone «Fai appello» per ogni server
dove ha un ban manuale attivo e gli appelli sono accesi.
Funzioni coperte: SPEC §23 (NF-30, issue #101)
Dipende da: core/ban_appeal_logic.py
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from core.ban_appeal_logic import (
    ATTESA_TRA_APPELLI,
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
from core.bounded_cache import BoundedCache
from core.database import db
from core.repositories.modmail_repo import modmail_repo
from core.ui_base import BaseModal, BaseView
from core.repositories.moderation_repo import moderation_repo
from cogs.moderation._tempban_modes import cancella_invito_per_codice
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
    # Controllo delle 24 ore e scrittura nello stesso blocco: tre invii insieme valgono uno.
    appello_id, ultimo = await moderation_repo.create_appeal_if_allowed(
        guild_id, utente.id, caso.case_number, testo.strip(), ATTESA_TRA_APPELLI
    )
    if appello_id is None:
        mancano = attesa_rimasta(ultimo, adesso)
        if mancano is None:  # l'orologio del test/del bot differisce da quello del database
            mancano = ATTESA_TRA_APPELLI
        return f"Hai già fatto appello. Puoi riprovare tra {attesa_a_parole(mancano)}."
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
        # Non è arrivato: non deve bloccare il prossimo tentativo per 24 ore.
        await moderation_repo.delete_appeal(appello_id)
        return "Non sono riuscito a consegnare l'appello allo staff: riprova più tardi."
    return "Appello inviato. Lo staff lo leggerà e riceverai una risposta qui."


class BottoneApriAppello(
    discord.ui.DynamicItem[discord.ui.Button], template=r"appello:apri:(?P<g>[0-9]+)"
):
    def __init__(self, guild_id: int, etichetta: str = "Fai appello") -> None:
        super().__init__(
            discord.ui.Button(
                label=etichetta[:80], style=discord.ButtonStyle.primary, custom_id=f"appello:apri:{guild_id}"
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


# Un messaggio tiene 25 bottoni (5 righe da 5).
MAX_SERVER_IN_DM = 25
# Il bottone in DM si offre al massimo una volta ogni 10 minuti per persona:
# il limite dei DM dello spam-trap (30 s) farebbe rispondere a quasi ogni messaggio.
OFFERTA_DM_OGNI_SECONDI = 600
_offerte_dm: BoundedCache[int, float] = BoundedCache(50_000)


async def offri_appello_in_dm(bot: discord.Client, utente: discord.abc.User, canale_dm) -> bool:
    """
    Chi scrive al bot in privato e ha un ban manuale attivo riceve un bottone
    «Fai appello» per ogni server con gli appelli accesi. True se ha risposto.
    Il limite di un appello ogni 24 ore resta quello del modulo.
    """
    ultima = _offerte_dm.get(utente.id)
    if ultima is not None and time.monotonic() - ultima < OFFERTA_DM_OGNI_SECONDI:
        return False
    # Chi ha una conversazione ModMail aperta scrive allo staff: il DM è del ModMail.
    if await modmail_repo.aperta_dell_utente(utente.id) is not None:
        return False
    casi = []
    for tipo in CASI_CON_APPELLO:
        casi += await moderation_repo.get_active_cases_for_user_across_guilds(utente.id, tipo)
    server: list[discord.Guild] = []
    for guild_id in dict.fromkeys(c.guild_id for c in casi):
        guild = bot.get_guild(guild_id)
        if guild is None or await db.get_guild_setting(guild_id, SETTING_CANALE_APPELLI) is None:
            continue
        server.append(guild)
        if len(server) == MAX_SERVER_IN_DM:
            break
    if not server:
        return False
    vista = BaseView(timeout=None)
    for guild in server:
        vista.add_item(BottoneApriAppello(guild.id, f"Appello: {guild.name}" if len(server) > 1 else "Fai appello"))
    nomi = ", ".join(f"**{g.name}**" for g in server)
    try:
        await canale_dm.send(
            truncate_text(f"Risulta un ban attivo a tuo nome su {nomi}.", 1800)
            + "\nPremi il bottone per fare appello (uno ogni 24 ore per server).",
            view=vista,
        )
    except discord.HTTPException:
        return False
    _offerte_dm.set(utente.id, time.monotonic())
    return True


# Appelli che qualcuno sta decidendo in questo momento (due clic insieme).
_APPELLI_IN_CORSO: set[int] = set()


async def _accetta(
    guild: discord.Guild, appello: dict, moderatore_id: int, client: discord.Client | None = None
) -> tuple[str | None, str | None]:
    """
    Toglie il ban contestato PRIMA di segnare l'appello come accettato.
    Restituisce (errore, testo per l'utente). Con un errore l'appello resta aperto.
    Se il caso contestato non è più attivo (ban già tolto, caso eliminato o
    sostituito) non si sbanna: l'appello si chiude e l'utente riceve il testo giusto.
    Tocca solo il caso dell'appello: un ban più recente non viene revocato.
    """
    uid = appello["user_id"]
    numero = appello["case_number"]
    caso = await moderation_repo.get_case(guild.id, numero) if numero is not None else None
    if caso is None or not caso.active:
        altro = None
        for tipo in CASI_CON_APPELLO:
            altro = altro or await moderation_repo.get_latest_active_case(guild.id, uid, tipo)
        if altro is not None:
            return None, (
                f"Il ban che contestavi su **{guild.name}** non è più in vigore, ma ne risulta "
                "un altro: per quello puoi fare un nuovo appello."
            )
        return None, f"Il ban su **{guild.name}** che contestavi risulta già tolto."
    try:
        await guild.unban(discord.Object(id=uid), reason=f"Appello #{appello['id']} accettato")
    except discord.NotFound:
        pass
    except discord.HTTPException:
        return "Non sono riuscito a togliere il ban: l'appello resta aperto. Controlla i miei permessi.", None
    await moderation_repo.revoke_case(guild.id, numero, moderatore_id)
    # La scadenza automatica di un tempban non serve più.
    await moderation_repo.cancel_tempban_jobs(guild.id, uid)
    stato_tempban = await moderation_repo.get_tempban_state(guild.id, uid)
    if stato_tempban is not None:
        await moderation_repo.mark_tempban_state_expired(guild.id, uid)
        await cancella_invito_per_codice(client, stato_tempban["invito_codice"])
    return None, None


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
    if appello["stato"] != STATO_APERTO or appello_id in _APPELLI_IN_CORSO:
        await interaction.response.send_message("Questo appello è già stato deciso.", ephemeral=True)
        return
    # Subito, senza await in mezzo: due clic insieme non passano entrambi.
    _APPELLI_IN_CORSO.add(appello_id)
    uid = appello["user_id"]
    avviso = ""
    testo_utente = None
    try:
        await interaction.response.defer()
        if accetta:
            esito, testo_utente = await _accetta(
                guild, appello, interaction.user.id, interaction.client
            )
            if esito is not None:
                # Il ban non è stato tolto: l'appello resta aperto, si può riprovare.
                await interaction.followup.send(esito, ephemeral=True)
                return
        if not await moderation_repo.decide_appeal(appello_id, stato, interaction.user.id):
            await interaction.followup.send("Questo appello è già stato deciso.", ephemeral=True)
            return
    finally:
        _APPELLI_IN_CORSO.discard(appello_id)
    messaggio = testo_utente or (
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
