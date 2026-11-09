"""
cogs/utility/eventi.py
======================
Eventi con iscrizioni: `/eventi crea|elenco|modifica|annulla`. Bottoni «Ci sono», «Forse», «Esco», «Iscritti» (persistenti),
lista d'attesa quando i posti finiscono, promemoria 15 minuti prima (scheduler), evento nativo di Discord a richiesta.
Chi crea ha il permesso Discord «Crea eventi».
Funzioni coperte: catalogo #128 UTL-113 (D69, B24)
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands

from core import eventi_logic as L
from core.admin_mentions_logic import utente_puo_pingare_ruoli
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.i18n import lingua_interazione, lingua_risposta, t
from core.programmati_logic import fuso_valido
from core.repositories.eventi_repo import eventi_repo
from core.repositories.utente_fuso_repo import utente_fuso_repo
from core.scheduler import scheduler
from core.ui_base import BaseView, _utente_o_server_in_blacklist

logger = logging.getLogger("iyokai.eventi")

AZIONE_PROMEMORIA = "evento_promemoria"
_NESSUNA_MENZIONE = discord.AllowedMentions.none()
_SCELTE = {"s": "si", "f": "forse", "e": "esco"}


def _aware(d: datetime) -> datetime:
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def puo_gestire(interaction: discord.Interaction, autore_id: int) -> bool:
    """L'autore, o chi ha «Gestisci eventi»."""
    return interaction.user.id == autore_id or bool(interaction.permissions.manage_events)


async def embed_evento(e, lingua: str) -> discord.Embed:
    c = await eventi_repo.conteggi(e["id"])
    annullato = e["stato"] != "attivo"
    quando = _aware(e["quando"])
    corpo = (e["descrizione"] or "")[: L.MAX_DESCRIZIONE]
    emb = discord.Embed(title=(("❌ " if annullato else "") + e["titolo"])[: L.MAX_TITOLO + 3], description=corpo,
                        colour=discord.Colour.dark_grey() if annullato else discord.Colour.green())
    emb.add_field(name=t("ev_campo_quando", lingua), value=f"{discord.utils.format_dt(quando, 'F')}\n{discord.utils.format_dt(quando, 'R')}",
                  inline=False)
    nomi = await eventi_repo.iscritti(e["id"], "si", L.MAX_NOMI_EMBED)
    elenco = " ".join(f"<@{u}>" for u in nomi) + (f" +{c['si'] - len(nomi)}" if c["si"] > len(nomi) else "")
    emb.add_field(name=t("ev_campo_si", lingua, posti=L.testo_posti(c["si"], e["posti"])), value=elenco or "-", inline=False)
    altri = [t("ev_forse_n", lingua, n=c["forse"])] if c["forse"] else []
    altri += [t("ev_attesa_n", lingua, n=c["attesa"])] if c["attesa"] else []
    if altri:
        emb.add_field(name=t("ev_campo_altri", lingua), value=" · ".join(altri), inline=False)
    emb.set_footer(text=t("ev_footer", lingua, id=e["id"]))
    return emb


def vista_evento(evento_id: int, lingua: str, *, spenta: bool = False) -> BaseView:
    vista = BaseView(timeout=None)
    if spenta:
        return vista
    for parte, chiave, stile in (("s", "ev_bottone_si", discord.ButtonStyle.success), ("f", "ev_bottone_forse", discord.ButtonStyle.secondary),
                                 ("e", "ev_bottone_esco", discord.ButtonStyle.danger), ("l", "ev_bottone_iscritti", discord.ButtonStyle.primary)):
        vista.add_item(BottoneEvento(evento_id, parte, t(chiave, lingua), stile))
    return vista


class BottoneEvento(discord.ui.DynamicItem[discord.ui.Button], template=r"ev:(?P<id>[0-9]+):(?P<p>[sfel])"):
    def __init__(self, evento_id: int, parte: str, etichetta: str = "…", stile: discord.ButtonStyle = discord.ButtonStyle.secondary) -> None:
        super().__init__(discord.ui.Button(label=etichetta[:80], style=stile, custom_id=f"ev:{evento_id}:{parte}"))
        self.evento_id, self.parte = evento_id, parte

    @classmethod
    async def from_custom_id(cls, interaction, item, match):
        return cls(int(match["id"]), match["p"])

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not await super().interaction_check(interaction):
            return False
        return not await _utente_o_server_in_blacklist(interaction)

    async def callback(self, interaction: discord.Interaction) -> None:
        cog = interaction.client.get_cog("EventiCog")
        if cog is None:
            return
        if self.parte == "l":
            await cog.mostra_iscritti(interaction, self.evento_id)
        else:
            await cog.scegli(interaction, self.evento_id, _SCELTE[self.parte])


class PaginaIscritti(BaseView):
    """Elenco degli iscritti a pagine, solo per chi l'ha aperto."""

    def __init__(self, proprietario: int, evento_id: int, pagina: int, totale: int, lingua: str) -> None:
        super().__init__(timeout=120)
        self.proprietario, self.evento_id, self.pagina, self.totale, self.lingua = proprietario, evento_id, pagina, totale, lingua
        self.indietro.label, self.avanti.label = "<", ">"
        self.indietro.disabled = pagina <= 0
        self.avanti.disabled = pagina >= L.pagine(totale) - 1

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not await super().interaction_check(interaction):
            return False
        if interaction.user.id != self.proprietario:
            await interaction.response.send_message(t("ev_non_tuo", await lingua_interazione(interaction)), ephemeral=True)
            return False
        return True

    @discord.ui.button(label="<", style=discord.ButtonStyle.secondary)
    async def indietro(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._vai(interaction, self.pagina - 1)

    @discord.ui.button(label=">", style=discord.ButtonStyle.secondary)
    async def avanti(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._vai(interaction, self.pagina + 1)

    async def _vai(self, interaction: discord.Interaction, pagina: int) -> None:
        testo, totale = await testo_iscritti(self.evento_id, pagina, self.lingua)
        nuova = PaginaIscritti(self.proprietario, self.evento_id, pagina, totale, self.lingua)
        await interaction.response.edit_message(content=testo, view=nuova, allowed_mentions=_NESSUNA_MENZIONE)


async def testo_iscritti(evento_id: int, pagina: int, lingua: str) -> tuple[str, int]:
    c = await eventi_repo.conteggi(evento_id)
    totale = sum(c.values())
    righe = await eventi_repo.tutti_gli_iscritti(evento_id, L.PER_PAGINA, pagina * L.PER_PAGINA)
    simbolo = {"si": t("ev_stato_si", lingua), "attesa": t("ev_stato_attesa", lingua), "forse": t("ev_stato_forse", lingua)}
    corpo = "\n".join(f"{simbolo[s]} <@{u}>" for u, s in righe) or t("ev_nessun_iscritto", lingua)
    return f"{corpo}\n\n{t('ev_pagina', lingua, pagina=pagina + 1, pagine=L.pagine(totale))}"[:1900], totale


async def _completa_eventi(interaction: discord.Interaction, attuale: str) -> list[app_commands.Choice[str]]:
    if interaction.guild is None:
        return []
    trovati = await eventi_repo.cerca(interaction.guild.id, attuale, datetime.now(timezone.utc))
    return [app_commands.Choice(name=f"#{r['id']} {r['titolo']}"[:100], value=str(r["id"])) for r in trovati][:25]


class EventiCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        await super().cog_load()
        self.bot.add_dynamic_items(BottoneEvento)
        scheduler.register_handler(AZIONE_PROMEMORIA, self.promemoria)

    async def cog_unload(self) -> None:
        self.bot.remove_dynamic_items(BottoneEvento)
        await super().cog_unload()

    # --- messaggio -------------------------------------------------------------------------------------------------
    async def aggiorna_messaggio(self, evento_id: int) -> None:
        e = await eventi_repo.prendi(evento_id)
        if e is None or not e["message_id"]:
            return
        canale = self.bot.get_channel(e["channel_id"])
        if canale is None:
            return
        lingua = await lingua_risposta(e["guild_id"], pubblica=True)
        try:
            await canale.get_partial_message(e["message_id"]).edit(
                embed=await embed_evento(e, lingua), view=vista_evento(e["id"], lingua, spenta=e["stato"] != "attivo"),
                allowed_mentions=_NESSUNA_MENZIONE)
        except discord.HTTPException as exc:
            logger.warning("Evento %s: messaggio non aggiornato (%s)", evento_id, exc)

    async def _avvisa_promossi(self, e, promossi: list[int]) -> None:
        canale = self.bot.get_channel(e["channel_id"])
        if not promossi or canale is None:
            return
        lingua = await lingua_risposta(e["guild_id"], pubblica=True)
        for u in promossi[:20]:
            try:
                await canale.send(t("ev_promosso", lingua, utente=f"<@{u}>", titolo=e["titolo"][:60]), delete_after=3600,
                                  allowed_mentions=discord.AllowedMentions(users=[discord.Object(u)], roles=False, everyone=False))
            except discord.HTTPException:
                return

    # --- bottoni ---------------------------------------------------------------------------------------------------
    async def scegli(self, interaction: discord.Interaction, evento_id: int, scelta: str) -> None:
        await interaction.response.defer(ephemeral=True)
        lingua = await lingua_interazione(interaction)
        e = await eventi_repo.prendi(evento_id)
        if e is None or interaction.guild is None or e["guild_id"] != interaction.guild.id:
            await interaction.followup.send(t("ev_non_trovato", lingua), ephemeral=True)
            return
        esito, stato, promossi = await eventi_repo.iscriviti(evento_id, interaction.user.id, scelta, datetime.now(timezone.utc))
        chiave = {"chiuso": "ev_chiuso", "niente": "ev_niente_da_togliere", "uguale": "ev_gia_cosi"}.get(esito)
        if chiave is None:
            chiave = {"si": "ev_iscritto_si", "forse": "ev_iscritto_forse", "attesa": "ev_iscritto_attesa", None: "ev_uscito"}[stato]
        await interaction.followup.send(t(chiave, lingua), ephemeral=True)
        if esito == "ok":
            await self.aggiorna_messaggio(evento_id)
            await self._avvisa_promossi(e, promossi)

    async def mostra_iscritti(self, interaction: discord.Interaction, evento_id: int) -> None:
        await interaction.response.defer(ephemeral=True)
        lingua = await lingua_interazione(interaction)
        if await eventi_repo.prendi(evento_id) is None:
            await interaction.followup.send(t("ev_non_trovato", lingua), ephemeral=True)
            return
        testo, totale = await testo_iscritti(evento_id, 0, lingua)
        await interaction.followup.send(testo, view=PaginaIscritti(interaction.user.id, evento_id, 0, totale, lingua), ephemeral=True,
                                        allowed_mentions=_NESSUNA_MENZIONE)

    # --- promemoria ------------------------------------------------------------------------------------------------
    async def _pianifica_promemoria(self, e) -> None:
        quando = _aware(e["quando"])
        ora = L.promemoria_a(quando, datetime.now(timezone.utc))
        if ora is not None:
            await scheduler.schedule(e["guild_id"], e["autore_id"], AZIONE_PROMEMORIA, ora,
                                     {"id": e["id"], "quando": int(quando.timestamp())})

    async def promemoria(self, guild_id: int, user_id: int, payload: dict) -> None:
        """Scheduler: avvisa chi ha detto «Ci sono». Se l'evento è stato spostato o annullato non fa nulla."""
        e = await eventi_repo.prendi(int(payload["id"]))
        if e is None or e["stato"] != "attivo" or int(_aware(e["quando"]).timestamp()) != int(payload["quando"]):
            return
        canale = self.bot.get_channel(e["channel_id"])
        if canale is None:
            return
        lingua = await lingua_risposta(e["guild_id"], pubblica=True)
        utenti = await eventi_repo.iscritti(e["id"], "si", 80)
        if not utenti:
            return
        testo = t("ev_promemoria", lingua, titolo=e["titolo"][:80], quando=discord.utils.format_dt(_aware(e["quando"]), "R"))
        menzioni = " ".join(f"<@{u}>" for u in utenti)
        try:
            await canale.send(f"{testo}\n{menzioni}"[:2000], allowed_mentions=discord.AllowedMentions(
                users=[discord.Object(u) for u in utenti], roles=False, everyone=False))
        except discord.HTTPException as exc:
            logger.warning("Evento %s: promemoria non inviato (%s)", e["id"], exc)

    # --- /eventi crea ----------------------------------------------------------------------------------------------
    @comando_di_gruppo("eventi", nome="crea", descrizione="Crea un evento con iscrizioni, posti e promemoria.")
    @app_commands.describe(
        titolo="Il titolo (massimo 100 caratteri)",
        quando="Data e ora (24/12/2026 21:00, nel tuo fuso) oppure tra quanto (3d, 5h)",
        posti="Quanti posti (massimo 500); con i posti pieni c'è la lista d'attesa",
        descrizione="Di cosa si tratta (massimo 1000 caratteri)",
        ruolo_ping="Un ruolo da avvisare (serve il permesso «Menziona tutti»)",
        canale="Dove pubblicarlo (di base questo canale)",
        evento_discord="Crea anche l'evento nativo di Discord",
    )
    async def crea(
        self, interaction: discord.Interaction, titolo: app_commands.Range[str, 1, L.MAX_TITOLO], quando: app_commands.Range[str, 2, 20],
        posti: app_commands.Range[int, 1, L.MAX_POSTI] | None = None, descrizione: app_commands.Range[str, 0, L.MAX_DESCRIZIONE] = "",
        ruolo_ping: discord.Role | None = None, canale: discord.TextChannel | None = None, evento_discord: bool = False,
    ) -> None:
        guild = interaction.guild
        lingua = await lingua_interazione(interaction)
        if guild is None:
            await interaction.response.send_message(t("guild_only_command", lingua), ephemeral=True)
            return
        if not (interaction.permissions.create_events or interaction.permissions.manage_events):
            await interaction.response.send_message(t("ev_serve_permesso", lingua), ephemeral=True)
            return
        adesso = datetime.now(timezone.utc)
        fuso = fuso_valido(await utente_fuso_repo.get(interaction.user.id))
        data = L.leggi_quando(quando, adesso, fuso)
        if isinstance(data, str):
            await interaction.response.send_message(t(f"ev_quando_{data}", lingua), ephemeral=True)
            return
        dove = canale or interaction.channel
        mio, suo = dove.permissions_for(guild.me), dove.permissions_for(interaction.user)
        if not (mio.view_channel and mio.send_messages and mio.embed_links and suo.send_messages):
            await interaction.response.send_message(t("ev_canale_non_ammesso", lingua), ephemeral=True)
            return
        if await eventi_repo.conta_aperti(guild.id, interaction.user.id, adesso) >= L.MAX_APERTI_PER_AUTORE:
            await interaction.response.send_message(t("ev_troppi", lingua, massimo=L.MAX_APERTI_PER_AUTORE), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        ping = ruolo_ping if ruolo_ping is not None and utente_puo_pingare_ruoli(interaction.user) else None
        eid = await eventi_repo.crea(guild.id, dove.id, interaction.user.id, titolo, descrizione, data, posti, ping.id if ping else None)
        e = await eventi_repo.prendi(eid)
        try:
            messaggio = await dove.send(
                ping.mention if ping else None, embed=await embed_evento(e, lingua), view=vista_evento(eid, lingua),
                allowed_mentions=discord.AllowedMentions(roles=[ping] if ping else False, users=False, everyone=False))
        except discord.HTTPException:
            await eventi_repo.elimina(eid)
            await interaction.followup.send(t("ev_non_pubblicato", lingua), ephemeral=True)
            return
        await eventi_repo.imposta_messaggio(eid, messaggio.id)
        await self._pianifica_promemoria(e)
        note = []
        if ruolo_ping is not None and ping is None:
            note.append(t("ev_ping_negato", lingua))
        if evento_discord:
            note.append(t("ev_discord_ok" if await self._crea_evento_discord(e, dove, messaggio.jump_url) else "ev_discord_no", lingua))
        await interaction.followup.send(" ".join([t("ev_creato", lingua, link=messaggio.jump_url), *note]), ephemeral=True)

    async def _crea_evento_discord(self, e, canale, link: str) -> bool:
        """L'evento nativo (esterno, 3 ore). Se manca il permesso al bot, l'evento del bot resta valido."""
        guild = self.bot.get_guild(e["guild_id"])
        if guild is None or not guild.me.guild_permissions.manage_events:
            return False
        inizio = _aware(e["quando"])
        try:
            nativo = await guild.create_scheduled_event(
                name=e["titolo"][: L.MAX_TITOLO], start_time=inizio, end_time=inizio + timedelta(hours=3),
                entity_type=discord.EntityType.external, privacy_level=discord.PrivacyLevel.guild_only,
                location=f"#{canale.name}"[:100], description=f"{(e['descrizione'] or '')[:900]}\n{link}"[:1000])
        except discord.HTTPException:
            logger.warning("Evento %s: evento nativo non creato", e["id"], exc_info=True)
            return False
        await eventi_repo.imposta_evento_discord(e["id"], nativo.id)
        return True

    async def _togli_evento_discord(self, e) -> None:
        guild = self.bot.get_guild(e["guild_id"])
        if guild is None or not e["discord_event_id"]:
            return
        try:
            nativo = guild.get_scheduled_event(e["discord_event_id"])
            if nativo is not None:
                await nativo.delete()
        except discord.HTTPException:
            logger.warning("Evento %s: evento nativo non tolto", e["id"], exc_info=True)

    # --- /eventi elenco --------------------------------------------------------------------------------------------
    @comando_di_gruppo("eventi", nome="elenco", descrizione="I prossimi eventi, o gli iscritti di un evento.")
    @app_commands.describe(evento="Un evento: ne mostra gli iscritti (scegli dall'elenco)")
    @app_commands.autocomplete(evento=_completa_eventi)
    async def elenco(self, interaction: discord.Interaction, evento: app_commands.Range[str, 1, 20] | None = None) -> None:
        lingua = await lingua_interazione(interaction)
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(t("guild_only_command", lingua), ephemeral=True)
            return
        if evento is None:
            righe = await eventi_repo.elenco(guild.id, datetime.now(timezone.utc))
            corpo = "\n".join(f"#{r['id']} · {discord.utils.format_dt(_aware(r['quando']), 'f')} · {r['titolo'][:60]}" for r in righe)
            await interaction.response.send_message(corpo[:1900] or t("ev_elenco_vuoto", lingua), ephemeral=True)
            return
        e = await eventi_repo.prendi(int(evento)) if evento.isdigit() else None
        if e is None or e["guild_id"] != guild.id:
            await interaction.response.send_message(t("ev_non_trovato", lingua), ephemeral=True)
            return
        testo, totale = await testo_iscritti(e["id"], 0, lingua)
        await interaction.response.send_message(f"**{e['titolo'][:100]}**\n{testo}"[:1990], view=PaginaIscritti(interaction.user.id, e["id"], 0, totale, lingua),
                                                ephemeral=True, allowed_mentions=_NESSUNA_MENZIONE)

    # --- /eventi modifica e annulla --------------------------------------------------------------------------------
    async def _evento_gestibile(self, interaction: discord.Interaction, evento: str, lingua: str):
        e = await eventi_repo.prendi(int(evento)) if evento.isdigit() else None
        if e is None or interaction.guild is None or e["guild_id"] != interaction.guild.id or e["stato"] != "attivo":
            await interaction.response.send_message(t("ev_non_trovato", lingua), ephemeral=True)
            return None
        if not puo_gestire(interaction, e["autore_id"]):
            await interaction.response.send_message(t("ev_non_si_puo", lingua), ephemeral=True)
            return None
        return e

    @comando_di_gruppo("eventi", nome="modifica", descrizione="Cambia titolo, data, posti o descrizione di un evento.")
    @app_commands.describe(evento="L'evento (scegli dall'elenco)", titolo="Nuovo titolo (massimo 100 caratteri)",
                           quando="Nuova data e ora, o tra quanto (3d, 5h)", posti="Nuovi posti (0 = senza limite)",
                           descrizione="Nuova descrizione (massimo 1000 caratteri)")
    @app_commands.autocomplete(evento=_completa_eventi)
    async def modifica(
        self, interaction: discord.Interaction, evento: app_commands.Range[str, 1, 20], titolo: app_commands.Range[str, 1, L.MAX_TITOLO] | None = None,
        quando: app_commands.Range[str, 2, 20] | None = None, posti: app_commands.Range[int, 0, L.MAX_POSTI] | None = None,
        descrizione: app_commands.Range[str, 1, L.MAX_DESCRIZIONE] | None = None,
    ) -> None:
        lingua = await lingua_interazione(interaction)
        e = await self._evento_gestibile(interaction, evento, lingua)
        if e is None:
            return
        data = None
        if quando:
            adesso = datetime.now(timezone.utc)
            data = L.leggi_quando(quando, adesso, fuso_valido(await utente_fuso_repo.get(interaction.user.id)))
            if isinstance(data, str):
                await interaction.response.send_message(t(f"ev_quando_{data}", lingua), ephemeral=True)
                return
        if titolo is None and data is None and posti is None and descrizione is None:
            await interaction.response.send_message(t("ev_niente_da_cambiare", lingua), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        promossi = await eventi_repo.modifica(e["id"], titolo=titolo, descrizione=descrizione, quando=data,
                                              posti=posti or None, togli_posti=posti == 0)
        if promossi is None:
            await interaction.followup.send(t("ev_non_trovato", lingua), ephemeral=True)
            return
        nuovo = await eventi_repo.prendi(e["id"])
        if data is not None:
            await self._pianifica_promemoria(nuovo)
        await self.aggiorna_messaggio(e["id"])
        await self._avvisa_promossi(nuovo, promossi)
        await interaction.followup.send(t("ev_modificato", lingua), ephemeral=True)

    @comando_di_gruppo("eventi", nome="annulla", descrizione="Annulla un evento: gli iscritti non possono più cambiare.")
    @app_commands.describe(evento="L'evento (scegli dall'elenco)")
    @app_commands.autocomplete(evento=_completa_eventi)
    async def annulla(self, interaction: discord.Interaction, evento: app_commands.Range[str, 1, 20]) -> None:
        lingua = await lingua_interazione(interaction)
        e = await self._evento_gestibile(interaction, evento, lingua)
        if e is None:
            return
        await interaction.response.defer(ephemeral=True)
        if not await eventi_repo.annulla(e["id"]):
            await interaction.followup.send(t("ev_non_trovato", lingua), ephemeral=True)
            return
        await self._togli_evento_discord(e)
        await self.aggiorna_messaggio(e["id"])
        await interaction.followup.send(t("ev_annullato", lingua), ephemeral=True)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> None:
        try:
            await eventi_repo.elimina_del_canale(channel.guild.id, channel.id)
        except Exception:
            logger.exception("Eventi: pulizia del canale %s fallita", channel.id)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(EventiCog(bot))
