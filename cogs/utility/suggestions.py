"""
cogs/utility/suggestions.py
==============================
Suggestion System (SPEC.md §14.14 — per i server clienti, distinto
da §14.8 che manda richieste al server dello sviluppatore). Un
membro propone, il server vota con reazioni native 👍👎, lo staff
decide con bottoni persistenti (approva/rifiuta) — stesso pattern di
View dinamica per-messaggio già collaudato per i Role Menu
(bot.add_view(view, message_id=...), ricostruita ad ogni avvio per
ogni suggestion ancora aperta). Catalogo #128: stati "in valutazione" e
"realizzato", motivo scritto dallo staff in una finestra, DM con l'esito
a chi ha proposto, copia dei suggerimenti decisi in un canale a parte.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from core import channel_router as router
from core.command_access import Livello, puo_usare
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.database import db
from core.i18n import testo_per
from core.premium import PremiumModule, registry
from core.leveling_logic import colore_valido
from core.repositories.suggestion_repo import Suggestion, suggestion_repo
from core.repositories.suggestions_config_repo import suggestions_config_repo
from core.suggestion_logic import (
    EMOJI_VOTO_SU,
    ESITI,
    colore_attuale,
    fuori_dal_canale_unico,
    APPROVED,
    CONSIDERING,
    IMPLEMENTED,
    MAX_MOTIVO,
    PENDING,
    REJECTED,
    can_decide,
    e_finale,
)
from core.ui_base import BaseModal, BaseView

logger = logging.getLogger("iyokai.suggestions")

MODULE_SUGGESTIONS = "suggestions"
SETTING_SUGGESTIONS_CHANNEL = "suggestions_channel_id"
SETTING_SUGGESTIONS_DECIDED_CHANNEL = "suggestions_decided_channel_id"

BUTTON_CUSTOM_ID_PREFIX = "iyokai_suggestion"


# (stato, etichetta del bottone, stile, parte del custom_id)
BOTTONI = (
    (APPROVED, "Approva", discord.ButtonStyle.success, "approve"),
    (REJECTED, "Rifiuta", discord.ButtonStyle.danger, "reject"),
    (CONSIDERING, "In valutazione", discord.ButtonStyle.secondary, "consider"),
    (IMPLEMENTED, "Realizzato", discord.ButtonStyle.primary, "implement"),
)
ETICHETTE = {
    PENDING: "In attesa",
    CONSIDERING: "🔎 In valutazione",
    APPROVED: "✅ Approvata",
    REJECTED: "❌ Rifiutata",
    IMPLEMENTED: "🚀 Realizzata",
}


def _build_embed(suggestion: Suggestion) -> discord.Embed:
    colori = {
        PENDING: discord.Color.blurple(),
        CONSIDERING: discord.Color.gold(),
        APPROVED: discord.Color.green(),
        REJECTED: discord.Color.red(),
        IMPLEMENTED: discord.Color.purple(),
    }

    embed = discord.Embed(
        title=f"💡 Suggerimento #{suggestion.id}",
        description=suggestion.suggestion_text,
        color=colori.get(suggestion.status, discord.Color.blurple()),
    )
    embed.add_field(
        name="Proposto da", value="Anonimo" if suggestion.anonimo else f"<@{suggestion.user_id}>", inline=True
    )
    embed.add_field(name="Stato", value=ETICHETTE.get(suggestion.status, suggestion.status), inline=True)
    if suggestion.decided_by is not None:
        embed.add_field(name="Deciso da", value=f"<@{suggestion.decided_by}>", inline=True)
    if suggestion.decision_reason:
        embed.add_field(name="Motivo", value=suggestion.decision_reason[:1024], inline=False)
    return embed


class BottoneChiScrisse(
    discord.ui.DynamicItem[discord.ui.Button], template=r"iyokai_suggestion:chi:(?P<id>[0-9]+)"
):
    """Solo per i suggerimenti anonimi: l'autore lo vede chi ha il livello admin, e la richiesta va nel registro."""

    def __init__(self, suggestion_id: int) -> None:
        super().__init__(
            discord.ui.Button(
                label="Chi l'ha scritto", style=discord.ButtonStyle.secondary,
                custom_id=f"{BUTTON_CUSTOM_ID_PREFIX}:chi:{suggestion_id}",
            )
        )
        self.suggestion_id = suggestion_id

    @classmethod
    async def from_custom_id(cls, interaction, item, match):
        return cls(int(match["id"]))

    async def callback(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None or not await puo_usare(interaction, Livello.ADMIN):
            await interaction.response.send_message(await testo_per(interaction, "suggestions_chi_solo_admin"), ephemeral=True)
            return
        suggestion = await suggestion_repo.get_suggestion(self.suggestion_id)
        if suggestion is None or suggestion.guild_id != interaction.guild.id:
            await interaction.response.send_message(
                await testo_per(interaction, "suggestions_questo_suggerimento_non_esiste_piu"), ephemeral=True
            )
            return
        logger.info("Suggerimento %s: autore svelato a %s", suggestion.id, interaction.user.id)
        await interaction.response.send_message(
            await testo_per(interaction, "suggestions_chi_risposta", id=suggestion.id, utente=f"<@{suggestion.user_id}> ({suggestion.user_id})"),
            ephemeral=True, allowed_mentions=discord.AllowedMentions.none(),
        )
        # Il registro: chi ha chiesto di vedere l'autore di un suggerimento anonimo (canale «moderazione»).
        destinazione = await router.destinazione(interaction.guild, router.TIPO_MODERAZIONE)
        if destinazione is not None:
            embed = discord.Embed(
                description=await testo_per(
                    interaction, "suggestions_chi_registro", pubblica=True, staff=interaction.user.mention, id=suggestion.id,
                ),
                color=discord.Color.orange(),
            )
            await router.invia_a(destinazione, interaction.guild, router.TIPO_MODERAZIONE, embed=embed)


class MotivoModal(BaseModal, title="Decisione sul suggerimento"):
    """Finestra con il motivo (facoltativo) prima di cambiare lo stato."""

    motivo = discord.ui.TextInput(
        label="Motivo (facoltativo)",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=MAX_MOTIVO,
    )

    def __init__(self, cog: "SuggestionsCog", suggestion_id: int, stato: str) -> None:
        super().__init__()
        self.cog = cog
        self.suggestion_id = suggestion_id
        self.stato = stato

    async def on_submit(self, interaction: discord.Interaction) -> None:
        testo = (self.motivo.value or "").strip() or None
        await self.cog._handle_decision(interaction, self.suggestion_id, self.stato, testo)


class SuggestionsCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    def _build_decision_view(self, suggestion_id: int, anonimo: bool = False) -> discord.ui.View:
        view = BaseView(timeout=None)
        if anonimo:
            view.add_item(BottoneChiScrisse(suggestion_id))
        for stato, etichetta, stile, chiave in BOTTONI:
            bottone: discord.ui.Button = discord.ui.Button(
                label=etichetta,
                style=stile,
                custom_id=f"{BUTTON_CUSTOM_ID_PREFIX}:{chiave}:{suggestion_id}",
            )
            bottone.callback = self._make_decision_callback(suggestion_id, stato)
            view.add_item(bottone)
        return view

    @staticmethod
    def _e_staff(interaction: discord.Interaction) -> bool:
        return isinstance(interaction.user, discord.Member) and interaction.user.guild_permissions.manage_guild

    def _make_decision_callback(self, suggestion_id: int, new_status: str):
        async def callback(interaction: discord.Interaction) -> None:
            if not self._e_staff(interaction):
                await interaction.response.send_message(
                    await testo_per(interaction, "suggestions_solo_lo_staff_puo_decidere"), ephemeral=True
                )
                return
            await interaction.response.send_modal(MotivoModal(self, suggestion_id, new_status))

        return callback

    async def _handle_decision(
        self,
        interaction: discord.Interaction,
        suggestion_id: int,
        new_status: str,
        motivo: str | None = None,
    ) -> None:
        if not self._e_staff(interaction):
            await interaction.response.send_message(
                await testo_per(interaction, "suggestions_solo_lo_staff_puo_decidere"), ephemeral=True
            )
            return

        suggestion = await suggestion_repo.get_suggestion(suggestion_id)
        if suggestion is None:
            await interaction.response.send_message(
                await testo_per(interaction, "suggestions_questo_suggerimento_non_esiste_piu"), ephemeral=True
            )
            return

        if not can_decide(suggestion.status) or suggestion.status == new_status:
            await interaction.response.send_message(
                await testo_per(interaction, "suggestions_questo_suggerimento_gia_stato_deciso"), ephemeral=True
            )
            return

        # Decisione atomica: se un altro membro dello staff ha cliccato un
        # istante prima, set_status risponde False e il suo esito resta.
        deciso = await suggestion_repo.set_status(
            suggestion_id,
            new_status,
            decided_by=interaction.user.id,
            decided_at=datetime.now(timezone.utc),
            motivo=motivo,
        )
        if not deciso:
            await interaction.response.send_message(
                await testo_per(interaction, "suggestions_questo_suggerimento_gia_stato_deciso"), ephemeral=True
            )
            return

        suggestion_aggiornata = await suggestion_repo.get_suggestion(suggestion_id)
        embed = _build_embed(suggestion_aggiornata)

        # Decisione finale: View vuota, non si può più cambiare idea.
        # In valutazione: i bottoni restano per la decisione vera.
        if e_finale(new_status):
            view = BaseView(timeout=None)
            if suggestion_aggiornata.anonimo:
                view.add_item(BottoneChiScrisse(suggestion_id))  # l'autore si può chiedere anche dopo
        else:
            view = self._build_decision_view(suggestion_id, suggestion_aggiornata.anonimo)
        opzioni = await suggestions_config_repo.get(interaction.guild.id)
        if opzioni.esito == "nuovo":
            # Il messaggio originale resta com'è (tolti i bottoni se è finito); l'esito è un messaggio nuovo.
            await interaction.response.edit_message(view=view)
            try:
                await interaction.message.reply(embed=embed, allowed_mentions=discord.AllowedMentions.none())
            except discord.HTTPException:
                logger.warning("Esito del suggerimento %s non pubblicato come messaggio nuovo.", suggestion_id)
        else:
            await interaction.response.edit_message(embed=embed, view=view)
        await self._avvisa_autore(interaction.guild, suggestion_aggiornata)
        if e_finale(new_status):
            await self._copia_nei_decisi(interaction.guild, suggestion_aggiornata)

    async def _avvisa_autore(self, guild: discord.Guild, suggestion: Suggestion) -> None:
        """UTL-137: DM a chi ha proposto, con lo stato e il motivo. Se i DM sono chiusi, pazienza."""
        membro = guild.get_member(suggestion.user_id)
        if membro is None:
            return
        testo = (
            f"Il tuo suggerimento #{suggestion.id} in **{guild.name}** è ora: "
            f"{ETICHETTE.get(suggestion.status, suggestion.status)}."
        )
        if suggestion.decision_reason:
            testo += f"\nMotivo: {suggestion.decision_reason}"
        try:
            await membro.send(testo[:2000], allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException:
            pass

    async def _copia_nei_decisi(self, guild: discord.Guild, suggestion: Suggestion) -> None:
        """UTL-138: copia del suggerimento deciso nel canale dei decisi, se impostato."""
        canale_id = await db.get_guild_setting(guild.id, SETTING_SUGGESTIONS_DECIDED_CHANNEL)
        canale = guild.get_channel(canale_id) if canale_id else None
        if not isinstance(canale, discord.TextChannel):
            return
        try:
            await canale.send(embed=_build_embed(suggestion), allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException:
            logger.warning("Suggerimento %s non copiato nel canale dei decisi.", suggestion.id)

    # ================================================================
    # Voti: colore a soglia
    # ================================================================
    async def _aggiorna_colore(self, payload: discord.RawReactionActionEvent) -> None:
        if payload.guild_id is None or str(payload.emoji) != EMOJI_VOTO_SU:
            return
        try:
            opzioni = await suggestions_config_repo.get(payload.guild_id)
            if opzioni.soglia <= 0 or not opzioni.colore:
                return
            suggestion = await suggestion_repo.per_messaggio(payload.message_id)
            if suggestion is None:
                return
            guild = self.bot.get_guild(payload.guild_id)
            canale = guild.get_channel(suggestion.channel_id) if guild else None
            if canale is None:
                return
            messaggio = await canale.fetch_message(payload.message_id)
            voti = next((r.count - (1 if r.me else 0) for r in messaggio.reactions if str(r.emoji) == EMOJI_VOTO_SU), 0)
            embed = _build_embed(suggestion)
            nuovo = colore_attuale(suggestion.status, voti, opzioni.soglia, opzioni.colore, embed.color.value)
            if messaggio.embeds and messaggio.embeds[0].color is not None and messaggio.embeds[0].color.value == nuovo:
                return
            embed.color = discord.Color(nuovo)
            await messaggio.edit(embed=embed)
        except discord.HTTPException:
            logger.warning("Colore a soglia del suggerimento %s non aggiornato.", payload.message_id)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        if payload.user_id != getattr(self.bot.user, "id", None):
            await self._aggiorna_colore(payload)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent) -> None:
        if payload.user_id != getattr(self.bot.user, "id", None):
            await self._aggiorna_colore(payload)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> None:
        try:
            await suggestions_config_repo.togli_canale(channel.guild.id, channel.id)
        except Exception:
            logger.exception("Suggerimenti: pulizia del canale %s fallita", channel.id)

    # ================================================================
    # Comandi
    # ================================================================
    @comando_di_gruppo(
        "admin-bot",
        nome="canale-suggerimenti",
        descrizione="Imposta il canale dei suggerimenti.",
        sottogruppo=("config", "Configurazione: canali, storico, ripristino ed esportazione"),
    )
    @app_commands.describe(
        channel="Il canale dove pubblicare i suggerimenti",
        decisi="Dove copiare i suggerimenti decisi (facoltativo)",
        anonimi="I suggerimenti non mostrano l'autore (lo vedono solo gli admin, col registro)",
        soglia="Voti 👍 per cambiare il colore del suggerimento (0 = spento)",
        colore="Il colore a soglia raggiunta, #RRGGBB",
        esito="La decisione modifica il messaggio o ne scrive uno nuovo",
        solo_da="Accetta /utility suggest solo da questo canale (rimettilo uguale per toglierlo)",
    )
    @app_commands.choices(esito=[app_commands.Choice(name="modifica il messaggio", value="modifica"), app_commands.Choice(name="messaggio nuovo", value="nuovo")])
    async def suggestion_setup(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        decisi: discord.TextChannel | None = None,
        anonimi: bool | None = None,
        soglia: app_commands.Range[int, 0, 10000] | None = None,
        colore: app_commands.Range[str, 7, 7] | None = None,
        esito: str | None = None,
        solo_da: discord.TextChannel | None = None,
    ) -> None:
        guild = interaction.guild
        if guild is None:
            return
        await db.set_guild_setting(guild.id, SETTING_SUGGESTIONS_CHANNEL, channel.id)
        testo = f"I suggerimenti verranno pubblicati in {channel.mention}."
        if decisi is not None:
            await db.set_guild_setting(guild.id, SETTING_SUGGESTIONS_DECIDED_CHANNEL, decisi.id)
            testo += f" Quelli decisi saranno copiati in {decisi.mention}."
        cambi: dict = {}
        if anonimi is not None:
            cambi["anonimi"] = anonimi
        if soglia is not None:
            cambi["soglia"] = soglia
        if colore is not None:
            valido = colore_valido(colore)
            if valido is None:
                await interaction.response.send_message(await testo_per(interaction, "suggestions_colore_non_valido"), ephemeral=True)
                return
            cambi["colore"] = valido
        if esito is not None and esito in ESITI:
            cambi["esito"] = esito
        if solo_da is not None:
            attuale = (await suggestions_config_repo.get(guild.id)).solo_canale_id
            cambi["solo_canale_id"] = None if attuale == solo_da.id else solo_da.id
        if cambi:
            await suggestions_config_repo.imposta(guild.id, **cambi)
            o = await suggestions_config_repo.get(guild.id)
            testo += "\n" + await testo_per(
                interaction, "suggestions_opzioni_stato",
                anonimi=await testo_per(interaction, "auto_si" if o.anonimi else "auto_no"), soglia=o.soglia,
                colore=o.colore or "—", esito=o.esito, solo=f"<#{o.solo_canale_id}>" if o.solo_canale_id else "—",
            )
        await interaction.response.send_message(testo, ephemeral=True, allowed_mentions=discord.AllowedMentions.none())

    @comando_di_gruppo(
        "utility",
        nome="suggest",
        descrizione="Proponi un'idea per questo server.",
    )
    @app_commands.describe(text="Il tuo suggerimento (massimo 2000 caratteri)")
    async def suggest(
        self, interaction: discord.Interaction, text: app_commands.Range[str, 1, 2000]
    ) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                await testo_per(interaction, "guild_only_command"), ephemeral=True
            )
            return

        if not await db.is_module_active_for_guild(guild.id, MODULE_SUGGESTIONS):
            await interaction.response.send_message(
                await testo_per(interaction, "ping_questo_modulo_non_attivo_su"),
                ephemeral=True,
            )
            return

        channel_id = await db.get_guild_setting(guild.id, SETTING_SUGGESTIONS_CHANNEL)
        if channel_id is None:
            await interaction.response.send_message(
                await testo_per(interaction, "suggestions_il_canale_dei_suggerimenti_non"),
                ephemeral=True,
            )
            return

        channel = guild.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message(
                await testo_per(interaction, "suggestions_il_canale_dei_suggerimenti_configurato"),
                ephemeral=True,
            )
            return

        opzioni = await suggestions_config_repo.get(guild.id)
        if fuori_dal_canale_unico(interaction.channel_id, opzioni.solo_canale_id):
            await interaction.response.send_message(
                await testo_per(interaction, "suggestions_solo_da_canale", canale=f"<#{opzioni.solo_canale_id}>"),
                ephemeral=True,
            )
            return

        # LIM-25: salvare, pubblicare e votare sono più chiamate: si risponde
        # subito con defer e l'esito arriva nel followup.
        await interaction.response.defer(ephemeral=True)
        suggestion_id = await suggestion_repo.create_suggestion(
            guild.id, channel.id, interaction.user.id, text, anonimo=opzioni.anonimi
        )
        suggestion = await suggestion_repo.get_suggestion(suggestion_id)
        embed = _build_embed(suggestion)
        view = self._build_decision_view(suggestion_id, suggestion.anonimo)

        try:
            messaggio = await channel.send(embed=embed, view=view)
        except discord.HTTPException as errore:
            # Mai lasciare una riga senza messaggio: nessuno la vedrebbe.
            await suggestion_repo.delete_suggestion(suggestion_id)
            motivo = (
                "Non ho i permessi per pubblicare nel canale dei suggerimenti."
                if isinstance(errore, discord.Forbidden)
                else "Discord ha rifiutato il messaggio."
            )
            await interaction.followup.send(
                await testo_per(interaction, "suggestions_il_suggerimento_non_stato_inviato", motivo=motivo), ephemeral=True
            )
            return

        await suggestion_repo.set_message_id(suggestion_id, messaggio.id)
        self.bot.add_view(view, message_id=messaggio.id)

        try:
            await messaggio.add_reaction("👍")
            await messaggio.add_reaction("👎")
        except discord.HTTPException:
            logger.warning(
                "Impossibile aggiungere le reazioni di voto al suggerimento %s.",
                suggestion_id,
            )

        await interaction.followup.send(
            await testo_per(interaction, "suggestions_suggerimento_pubblicato_in", mention=channel.mention), ephemeral=True
        )


async def setup(bot: commands.Bot) -> None:
    registry.register(
        PremiumModule(
            name=MODULE_SUGGESTIONS,
            display_name="Suggestions",
            category="community",
            description="Sistema di suggerimenti per i membri, con voto e decisione dello staff.",
            premium_capable=False,
        )
    )
    cog = SuggestionsCog(bot)
    await bot.add_cog(cog)
    bot.add_dynamic_items(BottoneChiScrisse)

    # Ricostruzione delle View dinamiche persistenti per OGNI
    # suggestion ancora in sospeso, ad ogni avvio — stesso principio
    # già usato per i Role Menu.
    for suggestion in await suggestion_repo.list_pending():
        view = cog._build_decision_view(suggestion.id, suggestion.anonimo)
        bot.add_view(view, message_id=suggestion.message_id)
