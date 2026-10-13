"""
cogs/utility/forms.py
=====================
Moduli e candidature (NF-34, SPEC §23): l'admin crea un modulo con fino a 5 domande
(candidatura staff, ingresso in un clan); chi lo compila lo fa in una finestra (modale) e la
risposta arriva in un canale dello staff con i bottoni Accetta e Rifiuta (persistenti).
Accettare può dare un ruolo. Una sola candidatura in attesa per persona e modulo.
Comandi: `/moduli candidature crea|elimina|elenco`, `/utility modulo`.
Funzioni coperte: SPEC §23 (NF-34)
"""

from __future__ import annotations

import logging

import asyncpg
import discord
from discord import app_commands
from discord.ext import commands

from core.command_access import Livello, autocomplete_protetto
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.database import db
from core.form_logic import (
    ACCEPTED, MAX_MODULI, MAX_NOME, MAX_RISPOSTA, MAX_TITOLO, REJECTED,
    campi_riepilogo, leggi_domande, puo_decidere,
)
from core.premium import PremiumModule, registry
from core.repositories.form_repo import Form, FormResponse, form_repo
from core.role_safety import check_role_assignable, motivo_ruolo_automatico_non_assegnabile
from core.ui_base import BaseModal, BaseView

logger = logging.getLogger("iyokai.forms")

MODULE_FORMS = "forms"
BUTTON_PREFIX = "iyokai_form"
_SG_MODULI = ("candidature", "Moduli e candidature")
_NESSUNA_MENZIONE = discord.AllowedMentions.none()
_NON_ATTIVO = (
    "Questo modulo non è attivo su questo server. Un amministratore può attivarlo con /admin setup attiva."
)


def embed_risposta(form: Form, risposta: FormResponse) -> discord.Embed:
    colori = {"pending": discord.Color.blurple(), ACCEPTED: discord.Color.green(), REJECTED: discord.Color.red()}
    etichette = {"pending": "In attesa", ACCEPTED: "✅ Accettata", REJECTED: "❌ Rifiutata"}
    embed = discord.Embed(
        title=f"📝 {form.title}"[:256], description=f"Candidato: <@{risposta.user_id}>", color=colori[risposta.status]
    )
    for nome, valore in campi_riepilogo(form.domande, risposta.risposte):
        embed.add_field(name=nome, value=valore, inline=False)
    embed.add_field(name="Stato", value=etichette[risposta.status], inline=True)
    if risposta.decided_by is not None:
        embed.add_field(name="Deciso da", value=f"<@{risposta.decided_by}>", inline=True)
    return embed


class FormModal(BaseModal):
    def __init__(self, cog: "FormsCog", form: Form) -> None:
        super().__init__(title=form.title[:MAX_TITOLO])
        self.cog, self.form = cog, form
        self._campi: list[discord.ui.TextInput] = []
        for d in form.domande:
            campo = discord.ui.TextInput(
                label=d.etichetta, required=True, max_length=MAX_RISPOSTA,
                style=discord.TextStyle.paragraph if d.lunga else discord.TextStyle.short,
            )
            self._campi.append(campo)
            self.add_item(campo)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await self.cog.invia_candidatura(interaction, self.form, [c.value for c in self._campi])


class FormsCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ---------------------------------------------------------------- bottoni dello staff
    def costruisci_view(self, response_id: int) -> discord.ui.View:
        view = BaseView(timeout=None)
        for azione, etichetta, stile, stato in (
            ("accept", "Accetta", discord.ButtonStyle.success, ACCEPTED),
            ("reject", "Rifiuta", discord.ButtonStyle.danger, REJECTED),
        ):
            bottone: discord.ui.Button = discord.ui.Button(
                label=etichetta, style=stile, custom_id=f"{BUTTON_PREFIX}:{azione}:{response_id}"
            )
            bottone.callback = self._callback_decisione(response_id, stato)
            view.add_item(bottone)
        return view

    def _callback_decisione(self, response_id: int, stato: str):
        async def callback(interaction: discord.Interaction) -> None:
            await self.decidi(interaction, response_id, stato)

        return callback

    async def decidi(self, interaction: discord.Interaction, response_id: int, stato: str) -> None:
        if not isinstance(interaction.user, discord.Member) or not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("Solo lo staff può decidere sulle candidature.", ephemeral=True)
            return
        risposta = await form_repo.get_response(response_id)
        form = await form_repo.get_form_by_id(risposta.form_id) if risposta else None
        if risposta is None or form is None:
            await interaction.response.send_message("Questa candidatura non esiste più.", ephemeral=True)
            return
        if not puo_decidere(risposta.status) or not await form_repo.decide(response_id, stato, interaction.user.id):
            await interaction.response.send_message("Questa candidatura è già stata decisa.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        decisa = await form_repo.get_response(response_id)
        try:
            await interaction.message.edit(embed=embed_risposta(form, decisa), view=None)
        except discord.HTTPException:
            logger.warning("Messaggio della candidatura %s non aggiornabile", response_id)
        note = []
        guild = interaction.guild
        if stato == ACCEPTED and form.accept_role_id is not None and guild is not None:
            note.append(await self._dai_ruolo(guild, form, risposta.user_id))
        await self._avvisa_candidato(guild, form, risposta.user_id, stato)
        await interaction.followup.send(
            ("Accettata." if stato == ACCEPTED else "Rifiutata.") + (" " + " ".join(n for n in note if n)).rstrip(),
            ephemeral=True,
        )

    async def _dai_ruolo(self, guild: discord.Guild, form: Form, user_id: int) -> str:
        motivo = motivo_ruolo_automatico_non_assegnabile(guild, form.accept_role_id)
        if motivo is not None:
            return f"Il ruolo non è stato dato: {motivo}"
        membro, ruolo = guild.get_member(user_id), guild.get_role(form.accept_role_id)
        if membro is None or ruolo is None:
            return "Il ruolo non è stato dato: il candidato ha lasciato il server."
        try:
            await membro.add_roles(ruolo, reason=f"Candidatura accettata: {form.name}")
        except discord.HTTPException:
            return "Il ruolo non è stato dato: Discord ha rifiutato."
        return "Ruolo dato."

    async def _avvisa_candidato(self, guild, form: Form, user_id: int, stato: str) -> None:
        membro = guild.get_member(user_id) if guild is not None else None
        if membro is None:
            return
        esito = "accettata" if stato == ACCEPTED else "rifiutata"
        try:
            await membro.send(f"La tua candidatura «{form.title}» su {guild.name} è stata {esito}.")
        except discord.HTTPException:
            pass  # DM chiusi: non è un errore

    # ---------------------------------------------------------------- invio
    async def invia_candidatura(self, interaction: discord.Interaction, form: Form, valori: list[str]) -> None:
        guild = interaction.guild
        canale = guild.get_channel(form.review_channel_id) if guild else None
        if canale is None:
            await interaction.response.send_message(
                "Il canale dove arrivano le candidature non esiste più: avvisa lo staff.", ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True)
        try:
            risposta_id = await form_repo.add_response(form, interaction.user.id, valori)
        except asyncpg.ForeignKeyViolationError:
            await interaction.followup.send("Questo modulo è stato eliminato mentre lo compilavi.", ephemeral=True)
            return
        if risposta_id is None:
            await interaction.followup.send("Hai già una candidatura in attesa per questo modulo.", ephemeral=True)
            return
        try:
            risposta = await form_repo.get_response(risposta_id)
            view = self.costruisci_view(risposta_id)
            messaggio = await canale.send(
                embed=embed_risposta(form, risposta), view=view, allowed_mentions=_NESSUNA_MENZIONE
            )
        except BaseException as errore:
            # Qualunque cosa vada storta prima che lo staff la veda: la candidatura si rilascia,
            # altrimenti la persona resterebbe bloccata da una "candidatura in attesa" invisibile.
            await form_repo.delete_response(risposta_id)
            if not isinstance(errore, discord.HTTPException):
                raise
            await interaction.followup.send(
                "Non sono riuscito a consegnare la candidatura allo staff (permessi del canale). Riprova più tardi.",
                ephemeral=True,
            )
            return
        await form_repo.set_review_message(risposta_id, messaggio.id)
        self.bot.add_view(view, message_id=messaggio.id)
        await interaction.followup.send("Candidatura inviata. Ti avviseremo in privato quando verrà decisa.", ephemeral=True)

    # ---------------------------------------------------------------- comandi
    async def _pronto(self, interaction: discord.Interaction) -> bool:
        if interaction.guild is None:
            await interaction.response.send_message("Questo comando è disponibile solo dentro un server.", ephemeral=True)
            return False
        if not await db.is_module_active_for_guild(interaction.guild.id, MODULE_FORMS):
            await interaction.response.send_message(_NON_ATTIVO, ephemeral=True)
            return False
        return True

    async def _nomi(self, interaction: discord.Interaction, current: str):
        if interaction.guild is None:
            return []
        moduli = await form_repo.list_forms(interaction.guild.id)
        return [app_commands.Choice(name=f.name, value=f.name) for f in moduli if current.lower() in f.name][:25]

    @autocomplete_protetto(Livello.ADMIN)
    async def _nomi_admin(self, interaction: discord.Interaction, current: str):
        return await self._nomi(interaction, current)

    async def _nomi_utente(self, interaction: discord.Interaction, current: str):
        return await self._nomi(interaction, current)

    @comando_di_gruppo("utility", nome="modulo", descrizione="Compila un modulo o una candidatura di questo server.")
    @app_commands.describe(nome="Il modulo da compilare")
    @app_commands.autocomplete(nome=_nomi_utente)
    async def modulo(self, interaction: discord.Interaction, nome: app_commands.Range[str, 1, MAX_NOME]) -> None:
        if not await self._pronto(interaction):
            return
        form = await form_repo.get_form(interaction.guild.id, nome)
        if form is None:
            await interaction.response.send_message("Non c'è nessun modulo con questo nome.", ephemeral=True)
            return
        await interaction.response.send_modal(FormModal(self, form))

    @comando_di_gruppo("moduli", nome="crea", descrizione="Crea un modulo o una candidatura.", sottogruppo=_SG_MODULI)
    @app_commands.describe(
        nome="Nome corto, senza spazi",
        titolo=f"Titolo della finestra (massimo {MAX_TITOLO} caratteri)",
        canale="Dove arrivano le candidature (solo staff)",
        domande="Fino a 5 domande separate da |; un + davanti vuol dire risposta lunga",
        ruolo="Ruolo dato a chi viene accettato (facoltativo)",
    )
    async def crea(
        self,
        interaction: discord.Interaction,
        nome: app_commands.Range[str, 1, MAX_NOME],
        titolo: app_commands.Range[str, 1, MAX_TITOLO],
        canale: discord.TextChannel,
        domande: app_commands.Range[str, 1, 1000],
        ruolo: discord.Role | None = None,
    ) -> None:
        if not await self._pronto(interaction):
            return
        elenco, errore = leggi_domande(domande)
        if errore:
            await interaction.response.send_message(errore, ephemeral=True)
            return
        permessi = canale.permissions_for(interaction.guild.me)
        if not (permessi.view_channel and permessi.send_messages and permessi.embed_links):
            await interaction.response.send_message(
                f"In {canale.mention} al bot servono i permessi per vedere, scrivere e incorporare link.",
                ephemeral=True, allowed_mentions=_NESSUNA_MENZIONE,
            )
            return
        if ruolo is not None:
            motivo = check_role_assignable(interaction.guild, ruolo, interaction.user, self_service=True)
            if motivo is not None:
                await interaction.response.send_message(motivo, ephemeral=True)
                return
        esito = await form_repo.create_form(
            interaction.guild.id, nome, titolo, canale.id, ruolo.id if ruolo else None, elenco, interaction.user.id
        )
        messaggi = {
            "ok": f"Modulo `{nome.lower()}` creato con {len(elenco)} domande. Chi vuole compilarlo usa `/utility modulo`.",
            "esiste": f"Esiste già un modulo `{nome.lower()}`: eliminalo prima con `/moduli candidature elimina`.",
            "pieno": f"Questo server ha già {MAX_MODULI} moduli: eliminane uno.",
        }
        await interaction.response.send_message(messaggi[esito], ephemeral=True)

    @comando_di_gruppo("moduli", nome="elimina", descrizione="Elimina un modulo e le sue risposte.", sottogruppo=_SG_MODULI)
    @app_commands.describe(nome="Il modulo da eliminare")
    @app_commands.autocomplete(nome=_nomi_admin)
    async def elimina(self, interaction: discord.Interaction, nome: app_commands.Range[str, 1, MAX_NOME]) -> None:
        if not await self._pronto(interaction):
            return
        fatto = await form_repo.delete_form(interaction.guild.id, nome)
        await interaction.response.send_message(
            "Modulo eliminato, insieme alle sue risposte." if fatto else "Non c'è nessun modulo con questo nome.",
            ephemeral=True,
        )

    @comando_di_gruppo("moduli", nome="elenco", descrizione="I moduli di questo server.", sottogruppo=_SG_MODULI)
    async def elenco(self, interaction: discord.Interaction) -> None:
        if not await self._pronto(interaction):
            return
        moduli = await form_repo.list_forms(interaction.guild.id)
        if not moduli:
            await interaction.response.send_message("Nessun modulo: creane uno con `/moduli candidature crea`.", ephemeral=True)
            return
        righe = [f"`{f.name}`: {f.title} ({len(f.domande)} domande) → <#{f.review_channel_id}>" for f in moduli]
        await interaction.response.send_message("\n".join(righe), ephemeral=True, allowed_mentions=_NESSUNA_MENZIONE)


async def setup(bot: commands.Bot) -> None:
    registry.register(
        PremiumModule(
            name=MODULE_FORMS,
            display_name="Moduli e candidature",
            category="utility",
            description="Moduli con domande, risposte allo staff con Accetta e Rifiuta.",
            premium_capable=False,
        )
    )
    cog = FormsCog(bot)
    await bot.add_cog(cog)
    for r in await form_repo.list_pending():
        bot.add_view(cog.costruisci_view(r.id), message_id=r.review_message_id)
