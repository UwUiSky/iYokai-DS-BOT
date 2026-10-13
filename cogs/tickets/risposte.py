"""
cogs/tickets/risposte.py
========================
Parte senza AI di #139 (AI-R-104, AI-R-105), accesa per pannello:

1. Risposte standard imparate dallo staff. Alla chiusura di un ticket in cui lo staff
   ha risposto, il bot propone nel canale dei log di salvare quella risposta (allegati
   compresi, ricaricati nel canale dei log). Lo staff Approva, Modifica o Scarta. Senza
   approvazione una risposta non si usa mai. Al ticket successivo, se le parole della
   richiesta corrispondono alle parole chiave di una risposta approvata, il bot la dà subito.
2. Sollecito. Se dopo N minuti nessuno dello staff ha risposto, il bot chiede all'utente di
   cosa ha bisogno; se la richiesta non ha una risposta standard, chiama il ruolo scelto
   per il pannello (o i ruoli di supporto).

Funziona anche con l'AI ferma: la ricerca è per parole (core/ticket_standard_logic.py).
La parte con l'AI (lingua dell'utente, scelta migliore, ruolo «giusto» secondo il caso)
si aggancia dopo (dev-ai). Il timer passa dallo scheduler (azione `ticket_sollecito`).
Comandi: `/gestione ticket-auto standard|sollecito|lista|modifica|elimina`.
Funzioni coperte: SPEC §25.97, §25.98
"""

from __future__ import annotations

import io
import logging

import discord
from discord import app_commands
from discord.ext import commands

from cogs.logging.basic_logs import SETTING_LOG_CHANNEL
from cogs.tickets.tickets import (
    TICKET_SOLLECITO_ACTION_TYPE,
    _is_ticket_staff,
    _support_role_ids,
)
from core import channel_router as router
from core import ticket_standard_logic as logica
from core.channel_router import TIPO_EVENTI
from core.command_access import Livello, autocomplete_protetto
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.database import db
from core.repositories.ticket_form_repo import PannelloTicket, ticket_form_repo
from core.repositories.ticket_repo import ticket_repo
from core.repositories.ticket_standard_repo import RispostaStandard, ticket_standard_repo
from core.scheduler import scheduler
from core.ui_base import BaseModal, BaseView, _rispondi_con_errore, _utente_o_server_in_blacklist

logger = logging.getLogger("iyokai.tickets.risposte")

GESTIONE_TICKET_AUTO = ("ticket-auto", "Ticket: risposte standard e sollecito")

_ESTENSIONI_IMMAGINE = (".png", ".jpg", ".jpeg", ".gif", ".webp")
MENZIONI_MASSIME = 5


def _candidate(risposte: list[RispostaStandard]) -> list[logica.Candidata]:
    return [
        logica.Candidata(r.id, frozenset(logica.parole_dal_testo_salvato(r.keywords)), r.use_count)
        for r in risposte
    ]


def embed_proposta(r: RispostaStandard, stato: str = "proposta") -> discord.Embed:
    colori = {"proposta": discord.Color.orange(), "approvata": discord.Color.green(), "scartata": discord.Color.dark_grey()}
    embed = discord.Embed(
        title=f"Risposta standard #{r.id} ({stato})",
        description=logica.taglia(r.body, 3500),
        color=colori.get(stato, discord.Color.orange()),
    )
    embed.add_field(name="Titolo", value=logica.taglia(r.title, 256), inline=False)
    embed.add_field(name="Parole chiave", value=logica.taglia(r.keywords, 1000) or "—", inline=False)
    if r.source_ticket_number is not None:
        embed.add_field(name="Nata dal ticket", value=f"#{r.source_ticket_number:04d}")
    if r.attachments:
        embed.add_field(
            name="Allegati",
            value=logica.taglia("\n".join(f"[{a['filename'][:60]}]({a['url']})" for a in r.attachments), 1000),
            inline=False,
        )
    return embed


def embed_risposta_automatica(r: RispostaStandard) -> discord.Embed:
    embed = discord.Embed(
        title="Forse ti serve questo",
        description=logica.taglia(r.body, 3800),
        color=discord.Color.blurple(),
    )
    immagine = next((a for a in r.attachments if a["filename"].lower().endswith(_ESTENSIONI_IMMAGINE)), None)
    if immagine is not None:
        embed.set_image(url=immagine["url"])
    altri = [a for a in r.attachments if a is not immagine]
    if altri:
        embed.add_field(
            name="Allegati",
            value=logica.taglia("\n".join(f"[{a['filename'][:60]}]({a['url']})" for a in altri), 1000),
            inline=False,
        )
    embed.set_footer(text="Risposta preparata dallo staff. Se non basta, aspetta: arriva una persona.")
    return embed


# ====================================================================
# Bottoni e finestra (persistenti: DynamicItem)
# ====================================================================
class ModuloRispostaStandard(BaseModal):
    def __init__(self, r: RispostaStandard) -> None:
        super().__init__(title=f"Risposta standard #{r.id}"[:45], timeout=600)
        self._id = r.id
        self.titolo = discord.ui.TextInput(
            label="Titolo", default=r.title, max_length=logica.MAX_TITOLO, custom_id="titolo"
        )
        self.parole = discord.ui.TextInput(
            label="Parole chiave (separate da virgola)", default=r.keywords,
            max_length=logica.MAX_PAROLE_TESTO, custom_id="parole",
        )
        self.corpo = discord.ui.TextInput(
            label="Risposta", default=r.body, style=discord.TextStyle.paragraph,
            max_length=logica.MAX_CORPO, custom_id="corpo",
        )
        for item in (self.titolo, self.parole, self.corpo):
            self.add_item(item)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        parole = logica.parole_da_testo_staff(self.parole.value)
        if not parole:
            await interaction.response.send_message(
                "Servono parole chiave vere (non solo «ciao», «grazie»…): senza, la risposta non scatterebbe mai.",
                ephemeral=True,
            )
            return
        corpo = self.corpo.value.strip()
        if not corpo:
            await interaction.response.send_message("La risposta non può essere vuota.", ephemeral=True)
            return
        if not await ticket_standard_repo.aggiorna(
            self._id, logica.taglia(self.titolo.value, logica.MAX_TITOLO), logica.parole_come_testo(parole), corpo
        ):
            await interaction.response.send_message("Questa risposta non esiste più.", ephemeral=True)
            return
        r = await ticket_standard_repo.per_id(self._id)
        await interaction.response.send_message(
            "Salvata." + (" Premi **Approva** per attivarla." if r and r.status == "proposed" else ""),
            ephemeral=True,
        )


class BottoneRispostaStandard(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"tkt:std:(?P<a>ok|mod|no):(?P<id>[0-9]+)",
):
    _ETICHETTE = {
        "ok": ("Approva", discord.ButtonStyle.success),
        "mod": ("Modifica", discord.ButtonStyle.secondary),
        "no": ("Scarta", discord.ButtonStyle.danger),
    }

    def __init__(self, azione: str, reply_id: int) -> None:
        etichetta, stile = self._ETICHETTE[azione]
        super().__init__(
            discord.ui.Button(label=etichetta, style=stile, custom_id=logica.custom_id_bottone(azione, reply_id))
        )
        self.azione = azione
        self.reply_id = reply_id

    @classmethod
    async def from_custom_id(cls, interaction, item, match):
        return cls(match["a"], int(match["id"]))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not await super().interaction_check(interaction):
            return False
        # SEC-10: un bottone dinamico non ha una BaseView sopra: la blacklist si controlla qui.
        if await _utente_o_server_in_blacklist(interaction):
            return False
        if not await _is_ticket_staff(interaction):
            await interaction.response.send_message(
                "Solo lo staff (permesso Manage Server o un ruolo di supporto) può decidere.", ephemeral=True
            )
            return False
        return True

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        logger.exception("Errore in un bottone delle risposte standard: %s", error)
        await _rispondi_con_errore(interaction)

    async def callback(self, interaction: discord.Interaction) -> None:
        r = await ticket_standard_repo.per_id(self.reply_id)
        if r is None or r.guild_id != (interaction.guild.id if interaction.guild else 0):
            await interaction.response.send_message("Questa proposta non esiste più.", ephemeral=True)
            return
        if self.azione == "mod":
            await interaction.response.send_modal(ModuloRispostaStandard(r))
            return
        if self.azione == "no":
            if r.status == "approved":
                await interaction.response.send_message(
                    "È già approvata: per toglierla usa `/gestione ticket-auto elimina`.", ephemeral=True
                )
                return
            await ticket_standard_repo.elimina(r.guild_id, r.id)
            await interaction.response.edit_message(embed=embed_proposta(r, "scartata"), view=None)
            return
        if not await ticket_standard_repo.approva(r.id, interaction.user.id):
            await interaction.response.send_message("Era già stata decisa.", ephemeral=True)
            return
        r = await ticket_standard_repo.per_id(r.id)
        await interaction.response.edit_message(embed=embed_proposta(r, "approvata"), view=_vista_approvata(r.id))


def _vista_proposta(reply_id: int) -> discord.ui.View:
    vista = BaseView(timeout=None)
    for azione in ("ok", "mod", "no"):
        vista.add_item(BottoneRispostaStandard(azione, reply_id))
    return vista


def _vista_approvata(reply_id: int) -> discord.ui.View:
    vista = BaseView(timeout=None)
    vista.add_item(BottoneRispostaStandard("mod", reply_id))
    return vista


@autocomplete_protetto(Livello.ADMIN)
async def completa_pannelli(interaction: discord.Interaction, corrente: str):
    if interaction.guild is None:
        return []
    pannelli = await ticket_form_repo.elenca_pannelli(interaction.guild.id)
    return [
        app_commands.Choice(name=p.name[:100], value=p.name[:100])
        for p in pannelli
        if corrente.strip().casefold() in p.name.casefold()
    ][:25]


# ====================================================================
# Cog
# ====================================================================
class RisposteStandardCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ---------------------------------------------------------------- proposta alla chiusura
    async def proponi_da_ticket(self, guild: discord.Guild, channel, ticket) -> None:
        """Chiamato da TicketsCog mentre il canale esiste ancora. Mai solleva verso chi chiude."""
        if ticket.panel_id is None or ticket.standard_reply_id is not None or ticket.first_response_at is None:
            return
        panel = await ticket_form_repo.pannello_per_id(ticket.panel_id)
        if panel is None or not panel.standard_attive:
            return
        if await ticket_standard_repo.conta(guild.id) >= logica.MAX_RISPOSTE_PER_SERVER:
            return

        storia: list[discord.Message] = []
        async for m in channel.history(limit=200, oldest_first=True):
            storia.append(m)
        coppia = logica.scegli_coppia(
            [logica.MessaggioStorico(m.author.id, m.author.bot, m.content or "", len(m.attachments)) for m in storia],
            ticket.user_id,
        )
        if coppia is None:
            return
        risposta_staff = storia[coppia.indice_risposta]
        testo_richiesta = coppia.richiesta + " " + (ticket.category_label or "")
        parole = logica.parole_chiave(testo_richiesta)
        if len(parole) < logica.MIN_PAROLE_CONDIVISE:
            return
        esistenti = await ticket_standard_repo.tutte_del_pannello(guild.id, panel.id)
        if logica.trova_migliore(_candidate(esistenti), testo_richiesta) is not None:
            return  # già coperta da una risposta salvata o in attesa di decisione

        predefinito = await db.get_guild_setting(guild.id, SETTING_LOG_CHANNEL)
        dest = await router.destinazione(guild, TIPO_EVENTI, predefinito)
        if dest is None:
            return  # nessun posto dove chiedere allo staff

        corpo = logica.taglia(risposta_staff.content or "(solo allegati)", logica.MAX_CORPO)
        proposta = await ticket_standard_repo.crea_proposta(
            guild.id, panel.id, logica.titolo_da(coppia.richiesta), logica.parole_come_testo(parole), corpo,
            ticket.ticket_number,
        )
        files = await self._copie_allegati(risposta_staff)
        try:
            messaggio = await dest.send(
                embed=embed_proposta(proposta), view=_vista_proposta(proposta.id), files=files,
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except discord.HTTPException:
            await ticket_standard_repo.elimina(guild.id, proposta.id)
            logger.warning("Proposta di risposta standard non inviata (server %s)", guild.id)
            return
        allegati = [{"filename": a.filename, "url": a.url} for a in getattr(messaggio, "attachments", [])]
        await ticket_standard_repo.imposta_messaggio(proposta.id, messaggio.id, allegati)
        if allegati:
            aggiornata = await ticket_standard_repo.per_id(proposta.id)
            try:
                await messaggio.edit(embed=embed_proposta(aggiornata))
            except discord.HTTPException:
                pass

    @staticmethod
    async def _copie_allegati(messaggio: discord.Message) -> list[discord.File]:
        """Ricarica gli allegati nel canale dei log: i link del ticket spariscono con il canale."""
        allegati = list(messaggio.attachments)
        file: list[discord.File] = []
        for i in logica.allegati_da_scaricare([a.size for a in allegati]):
            try:
                contenuto = await allegati[i].read()
            except discord.HTTPException:
                continue
            file.append(discord.File(io.BytesIO(contenuto), filename=allegati[i].filename))
        return file

    # ---------------------------------------------------------------- uso nei ticket
    async def su_messaggio_dell_utente(self, message: discord.Message, ticket) -> None:
        """Chiamato da TicketsCog per i messaggi di chi ha aperto un ticket ancora senza risposta dello staff."""
        if ticket.first_response_at is not None or ticket.panel_id is None:
            return
        if ticket.standard_reply_id is not None or ticket.escalato_at is not None:
            return
        panel = await ticket_form_repo.pannello_per_id(ticket.panel_id)
        if panel is None or not (panel.standard_attive or panel.sollecito_minuti):
            return
        await ticket_repo.mark_user_wrote(message.channel.id)
        if panel.standard_attive:
            approvate = await ticket_standard_repo.approvate(ticket.guild_id, panel.id)
            scelta = logica.trova_migliore(_candidate(approvate), message.content or "")
            if scelta is not None and await ticket_repo.mark_standard_reply(message.channel.id, scelta.id):
                risposta = next(r for r in approvate if r.id == scelta.id)
                await ticket_standard_repo.usata(risposta.id)
                try:
                    await message.channel.send(
                        embed=embed_risposta_automatica(risposta), reference=message,
                        allowed_mentions=discord.AllowedMentions.none(),
                    )
                except discord.HTTPException:
                    logger.warning("Risposta standard non inviata nel ticket %s", message.channel.id)
                return
        if ticket.sollecito_at is not None:
            await self._chiama_lo_staff(message.channel, ticket, panel)

    async def _chiama_lo_staff(self, channel, ticket, panel: PannelloTicket) -> None:
        if not await ticket_repo.mark_escalation(channel.id):
            return
        ruoli = [panel.ruolo_escalation] if panel.ruolo_escalation else (await _support_role_ids(ticket.guild_id))[:MENZIONI_MASSIME]
        menzioni = " ".join(f"<@&{r}>" for r in ruoli)
        testo = f"{menzioni} <@{ticket.user_id}> aspetta una risposta" if menzioni else f"<@{ticket.user_id}> aspetta una risposta"
        try:
            await channel.send(
                testo + " e per questa richiesta non c'è una risposta pronta.",
                allowed_mentions=discord.AllowedMentions(roles=[discord.Object(id=r) for r in ruoli], users=False),
            )
        except discord.HTTPException:
            logger.warning("Chiamata allo staff non inviata nel ticket %s", channel.id)

    async def handle_ticket_sollecito(self, guild_id: int, user_id: int, payload: dict) -> None:
        """Handler dello scheduler. Se solleva, lo scheduler riprova più tardi."""
        channel_id = payload["channel_id"]
        ticket = await ticket_repo.get_ticket_by_channel(channel_id)
        if (
            ticket is None
            or ticket.status != "open"
            or ticket.first_response_at is not None
            or ticket.standard_reply_id is not None
            or ticket.panel_id is None
        ):
            return
        panel = await ticket_form_repo.pannello_per_id(ticket.panel_id)
        if panel is None or not panel.sollecito_minuti:
            return
        if not await ticket_repo.mark_sollecito(channel_id):
            return
        channel = self.bot.get_channel(channel_id)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(channel_id)
            except discord.NotFound:
                return
        if ticket.utente_scritto_at is not None:
            # Ha già scritto e nessuna risposta pronta ha scattato: serve una persona.
            await self._chiama_lo_staff(channel, ticket, panel)
            return
        try:
            await channel.send(
                f"<@{ticket.user_id}> nessuno dello staff ha ancora risposto. "
                "Di cosa hai bisogno? Scrivilo qui: cerco una risposta già pronta, altrimenti avviso lo staff.",
                allowed_mentions=discord.AllowedMentions(users=[discord.Object(id=ticket.user_id)]),
            )
        except discord.HTTPException:
            logger.warning("Sollecito non inviato nel ticket %s", channel_id)

    # ---------------------------------------------------------------- comandi
    async def _pannello(self, interaction: discord.Interaction, nome: str) -> PannelloTicket | None:
        if interaction.guild is None:
            return None
        panel = await ticket_form_repo.pannello_per_nome(interaction.guild.id, nome.strip())
        if panel is None:
            await interaction.response.send_message(f"Nessun pannello chiamato **{nome.strip()[:100]}**.", ephemeral=True)
        return panel

    @comando_di_gruppo(
        "gestione",
        nome="standard",
        descrizione="Accendi o spegni le risposte standard imparate dallo staff per un pannello.",
        sottogruppo=GESTIONE_TICKET_AUTO,
    )
    @app_commands.describe(pannello="Il pannello", attive="Sì per proporle e usarle, no per spegnerle")
    @app_commands.autocomplete(pannello=completa_pannelli)
    async def standard(
        self, interaction: discord.Interaction, pannello: app_commands.Range[str, 1, 50], attive: bool
    ) -> None:
        panel = await self._pannello(interaction, pannello)
        if panel is None:
            return
        await ticket_form_repo.imposta_standard(panel.id, attive)
        testo = (
            f"Risposte standard accese per **{panel.name}**: alla chiusura di un ticket con risposta dello staff "
            "trovi la proposta nel canale dei log. Nulla si usa senza la tua approvazione."
            if attive
            else f"Risposte standard spente per **{panel.name}** (quelle già salvate restano)."
        )
        await interaction.response.send_message(testo, ephemeral=True)

    @comando_di_gruppo(
        "gestione",
        nome="sollecito",
        descrizione="Dopo N minuti senza risposta dello staff, il bot chiede all'utente di cosa ha bisogno.",
        sottogruppo=GESTIONE_TICKET_AUTO,
    )
    @app_commands.describe(
        pannello="Il pannello",
        minuti="Minuti di attesa (da 1 a 1440), 0 per spegnere",
        ruolo="Chi chiamare se non c'è una risposta pronta (predefinito: i ruoli di supporto)",
    )
    @app_commands.autocomplete(pannello=completa_pannelli)
    async def sollecito(
        self,
        interaction: discord.Interaction,
        pannello: app_commands.Range[str, 1, 50],
        minuti: app_commands.Range[int, 0, logica.MAX_MINUTI_SOLLECITO],
        ruolo: discord.Role | None = None,
    ) -> None:
        panel = await self._pannello(interaction, pannello)
        if panel is None:
            return
        try:
            valore = logica.minuti_sollecito_validi(minuti)
        except ValueError as errore:
            await interaction.response.send_message(str(errore), ephemeral=True)
            return
        await ticket_form_repo.imposta_sollecito(panel.id, valore, ruolo.id if (ruolo and valore) else None)
        if valore is None:
            testo = f"Sollecito spento per **{panel.name}**."
        else:
            chi = ruolo.mention if ruolo else "i ruoli di supporto"
            testo = (
                f"Nei ticket di **{panel.name}** senza risposta dello staff dopo {valore} minuti il bot chiede all'utente "
                f"di cosa ha bisogno; se non ha una risposta pronta chiama {chi} (vale per i ticket aperti da ora in poi)."
            )
        await interaction.response.send_message(testo, ephemeral=True, allowed_mentions=discord.AllowedMentions.none())

    @comando_di_gruppo(
        "gestione",
        nome="lista",
        descrizione="Elenca le risposte standard del server.",
        sottogruppo=GESTIONE_TICKET_AUTO,
    )
    @app_commands.describe(stato="Quali mostrare (predefinito: tutte)")
    @app_commands.choices(
        stato=[
            app_commands.Choice(name="approvate", value="approved"),
            app_commands.Choice(name="in attesa", value="proposed"),
        ]
    )
    async def lista(self, interaction: discord.Interaction, stato: app_commands.Choice[str] | None = None) -> None:
        if interaction.guild is None:
            return
        risposte = await ticket_standard_repo.elenca(interaction.guild.id, stato.value if stato else None, 25)
        if not risposte:
            await interaction.response.send_message("Nessuna risposta standard.", ephemeral=True)
            return
        righe = [
            f"`#{r.id}` {'✅' if r.status == 'approved' else '⏳'} {logica.taglia(r.title, 60)} · usata {r.use_count} volte"
            for r in risposte
        ]
        await interaction.response.send_message(logica.taglia("\n".join(righe), 1900), ephemeral=True)

    @comando_di_gruppo(
        "gestione",
        nome="modifica",
        descrizione="Correggi titolo, parole chiave e testo di una risposta standard.",
        sottogruppo=GESTIONE_TICKET_AUTO,
    )
    @app_commands.describe(numero="Il numero della risposta (da /gestione ticket-auto lista)")
    async def modifica(self, interaction: discord.Interaction, numero: app_commands.Range[int, 1, 2**31 - 1]) -> None:
        r = await ticket_standard_repo.per_id(numero)
        if r is None or interaction.guild is None or r.guild_id != interaction.guild.id:
            await interaction.response.send_message("Nessuna risposta con questo numero.", ephemeral=True)
            return
        await interaction.response.send_modal(ModuloRispostaStandard(r))

    @comando_di_gruppo(
        "gestione",
        nome="elimina",
        descrizione="Elimina una risposta standard.",
        sottogruppo=GESTIONE_TICKET_AUTO,
    )
    @app_commands.describe(numero="Il numero della risposta (da /gestione ticket-auto lista)")
    async def elimina(self, interaction: discord.Interaction, numero: app_commands.Range[int, 1, 2**31 - 1]) -> None:
        if interaction.guild is None:
            return
        if await ticket_standard_repo.elimina(interaction.guild.id, numero):
            await interaction.response.send_message(f"Risposta #{numero} eliminata.", ephemeral=True)
        else:
            await interaction.response.send_message("Nessuna risposta con questo numero.", ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    cog = RisposteStandardCog(bot)
    await bot.add_cog(cog)
    scheduler.register_handler(TICKET_SOLLECITO_ACTION_TYPE, cog.handle_ticket_sollecito)
    bot.add_dynamic_items(BottoneRispostaStandard)
