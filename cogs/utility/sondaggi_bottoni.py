"""
cogs/utility/sondaggi_bottoni.py
================================
Sondaggio a bottoni del bot: `/sondaggi bottoni` (fino a 20 opzioni, anonimo, risultati alla fine, più scelte, ruolo riservato,
voti pesati per ruolo, chiusura a N votanti), `/sondaggi modifica` (finestra), `/sondaggi gestisci` (elenco, riepilogo, chiudi), inizio programmato (`inizia_tra`) e `/admin-moduli sondaggi` (pesi per ruolo).
I bottoni sono DynamicItem: funzionano dopo il riavvio. La scadenza passa dallo scheduler. Chi esce o è bannato perde il voto.
Funzioni coperte: catalogo #128 UTL-088, 089, 091, 093, 094, 096, 090, 097 (D69, B22, B23)
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands

from core import sondaggi_logic as L
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.database import db
from core.duration_logic import parse_duration
from core.i18n import lingua_interazione, lingua_risposta, t
from core.repositories.sondaggi_nativi_repo import sondaggi_nativi_repo
from core.repositories.sondaggi_repo import sondaggi_repo
from core.scheduler import scheduler
from core.ui_base import BaseModal, BaseView, _utente_o_server_in_blacklist

logger = logging.getLogger("iyokai.sondaggi")

MODULE_POLL = "poll"
AZIONE_CHIUDI = "sondaggio_chiudi"
AZIONE_APRI = "sondaggio_apri"
MAX_APERTI_PER_AUTORE = 5
DURATA_MASSIMA = 30 * 86400
DURATA_MINIMA = 60
SECONDI_CONFERMA = 60
_NESSUNA_MENZIONE = discord.AllowedMentions.none()
_SG_ADMIN = ("sondaggi", "Sondaggi: peso del voto per ruolo")
_AZIONI_PESO = [
    app_commands.Choice(name="imposta", value="imposta"),
    app_commands.Choice(name="togli", value="togli"),
    app_commands.Choice(name="elenco", value="elenco"),
]
_RISULTATI = [app_commands.Choice(name="subito", value="subito"), app_commands.Choice(name="alla fine", value="alla_fine")]


def _aware(d: datetime) -> datetime:
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def vista_sondaggio(sondaggio_id: int, opzioni: list[str], *, chiuso: bool = False, lingua: str = "it") -> BaseView:
    """Le righe di bottoni: opzioni (5 per riga) e, in fondo, Risultati, Togli voto, Gestisci."""
    vista = BaseView(timeout=None)
    if chiuso:
        return vista
    nomi = {"r": t("sb_bottone_risultati", lingua), "t": t("sb_bottone_togli", lingua), "g": t("sb_bottone_gestisci", lingua)}
    for riga, voci in enumerate(L.righe_bottoni(len(opzioni))):
        for tipo, valore in voci:
            etichetta = L.etichetta_bottone(valore, opzioni[valore]) if tipo == "opzione" else nomi[valore]
            vista.add_item(BottoneSondaggio(sondaggio_id, valore, etichetta, riga))
    return vista


class BottoneSondaggio(discord.ui.DynamicItem[discord.ui.Button], template=r"sb:(?P<id>[0-9]+):(?P<p>[0-9]+|[rtg])"):
    def __init__(self, sondaggio_id: int, parte: int | str, etichetta: str = "…", riga: int | None = None) -> None:
        stile = discord.ButtonStyle.primary if isinstance(parte, int) else discord.ButtonStyle.secondary
        super().__init__(discord.ui.Button(label=etichetta[: L.ETICHETTA_BOTTONE], style=stile,
                                           custom_id=L.custom_id(sondaggio_id, parte), row=riga))
        self.sondaggio_id, self.parte = sondaggio_id, parte

    @classmethod
    async def from_custom_id(cls, interaction, item, match):
        p = match["p"]
        return cls(int(match["id"]), int(p) if p.isdigit() else p)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not await super().interaction_check(interaction):
            return False
        # Un bottone dinamico non ha una BaseView sopra: la blacklist si controlla qui.
        return not await _utente_o_server_in_blacklist(interaction)

    async def callback(self, interaction: discord.Interaction) -> None:
        cog = interaction.client.get_cog("SondaggiBottoniCog")
        if cog is None:
            return
        if isinstance(self.parte, int):
            await cog.voto(interaction, self.sondaggio_id, self.parte)
        elif self.parte == "r":
            await cog.mostra_risultati(interaction, self.sondaggio_id)
        elif self.parte == "t":
            await cog.togli_voto(interaction, self.sondaggio_id)
        else:
            await cog.apri_gestione(interaction, self.sondaggio_id)


def puo_gestire(interaction: discord.Interaction, autore_id: int) -> bool:
    """L'autore, o chi nel canale ha «Gestisci messaggi»."""
    return interaction.user.id == autore_id or bool(interaction.permissions.manage_messages)


async def embed_sondaggio(s, opzioni: list[str], risultati: list[tuple[str, int]], votanti: int, lingua: str, *, chiuso: bool) -> discord.Embed:
    mostra = chiuso or s["risultati"] == "subito"
    if mostra:
        corpo = "\n".join(L.righe_risultati(risultati))
    else:
        corpo = "\n".join(f"**{n + 1}.** {o}" for n, o in enumerate(opzioni)) + "\n\n" + t("sb_risultati_nascosti", lingua)
    e = discord.Embed(title=s["domanda"][: L.MAX_DOMANDA], description=corpo[:4000],
                      colour=discord.Colour.dark_grey() if chiuso else discord.Colour.blurple())
    note = [t("sb_nota_anonimo", lingua)] if s["anonimo"] else []
    note += [t("sb_nota_multipla", lingua)] if s["multipla"] else []
    note += [t("sb_nota_pesato", lingua)] if s["pesato"] else []
    note += [t("sb_nota_ruoli", lingua, ruoli=" ".join(f"<@&{r}>" for r in s["ruoli"][:10]))] if s["ruoli"] else []
    if note:
        e.add_field(name=t("sb_campo_regole", lingua), value=" · ".join(note)[:1000], inline=False)
    if chiuso:
        e.set_footer(text=t("sb_chiuso", lingua, votanti=votanti))
    elif s["scade_il"]:
        e.add_field(name=t("sb_campo_scade", lingua), value=discord.utils.format_dt(_aware(s["scade_il"]), "R"), inline=True)
    return e


class ModaleModifica(BaseModal):
    def __init__(self, cog: "SondaggiBottoniCog", s, opzioni: list[str], lingua: str) -> None:
        super().__init__(title=t("sb_modifica_titolo", lingua)[:45], timeout=300)
        self.cog, self.sid, self.autore, self.lingua = cog, s["id"], s["autore_id"], lingua
        self.domanda = discord.ui.TextInput(label=t("sb_modifica_domanda", lingua)[:45], default=s["domanda"][: L.MAX_DOMANDA],
                                            max_length=L.MAX_DOMANDA)
        self.opzioni = discord.ui.TextInput(label=t("sb_modifica_opzioni", lingua)[:45], style=discord.TextStyle.paragraph,
                                            default="\n".join(opzioni)[:1700], max_length=1700)
        self.durata = discord.ui.TextInput(label=t("sb_modifica_durata", lingua)[:45], required=False, max_length=6, placeholder="24h")
        for c in (self.domanda, self.opzioni, self.durata):
            self.add_item(c)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await self.cog.applica_modifica(interaction, self.sid, self.domanda.value, self.opzioni.value, self.durata.value)


class ConfermaModifica(BaseView):
    """Togliere un'opzione già votata cancella quei voti: serve la conferma di chi ha chiesto la modifica."""

    def __init__(self, cog: "SondaggiBottoniCog", proprietario: int, sid: int, domanda: str, opzioni: list[str],
                 scade_il: datetime | None, etichette: tuple[str, str]) -> None:
        super().__init__(timeout=SECONDI_CONFERMA)
        self.cog, self.proprietario, self.sid = cog, proprietario, sid
        self.domanda, self.opzioni, self.scade_il = domanda, opzioni, scade_il
        self.conferma.label, self.annulla.label = etichette[0][:80], etichette[1][:80]

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not await super().interaction_check(interaction):
            return False
        if interaction.user.id != self.proprietario:
            await interaction.response.send_message(await _testo(interaction, "sb_non_e_tuo"), ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Conferma", style=discord.ButtonStyle.danger)
    async def conferma(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.stop()  # anti-doppio-clic prima di ogni await
        await interaction.response.defer()
        s = await sondaggi_repo.prendi(self.sid)
        if s is None or not puo_gestire(interaction, s["autore_id"]):  # il permesso si ricontrolla al tasto
            await interaction.edit_original_response(content=await _testo(interaction, "sb_non_e_tuo"), view=None)
            return
        esito = await self.cog.scrivi_modifica(self.sid, self.domanda, self.opzioni, self.scade_il)
        await interaction.edit_original_response(content=await _testo(interaction, esito), view=None)

    @discord.ui.button(label="Annulla", style=discord.ButtonStyle.secondary)
    async def annulla(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.stop()
        await interaction.response.edit_message(content=await _testo(interaction, "sb_annullato"), view=None)


class GestioneSondaggio(BaseView):
    """Il pannello di «Gestisci»: chiudi ora e scegli i ruoli che possono votare. Ogni tasto ricontrolla il permesso."""

    def __init__(self, cog: "SondaggiBottoniCog", proprietario: int, sid: int, etichette: tuple[str, str]) -> None:
        super().__init__(timeout=120)
        self.cog, self.proprietario, self.sid = cog, proprietario, sid
        self.chiudi.label = etichette[0][:80]
        self.ruoli.placeholder = etichette[1][:150]

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not await super().interaction_check(interaction):
            return False
        if interaction.user.id != self.proprietario:
            await interaction.response.send_message(await _testo(interaction, "sb_non_e_tuo"), ephemeral=True)
            return False
        return True

    async def _autorizzato(self, interaction: discord.Interaction):
        s = await sondaggi_repo.prendi(self.sid)
        if s is None or s["stato"] != "aperto" or not puo_gestire(interaction, s["autore_id"]):
            return None
        return s

    @discord.ui.button(label="Chiudi ora", style=discord.ButtonStyle.danger, row=1)
    async def chiudi(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.stop()  # anti-doppio-clic prima di ogni await
        await interaction.response.defer()
        if await self._autorizzato(interaction) is None:
            await interaction.edit_original_response(content=await _testo(interaction, "sb_non_si_puo"), view=None)
            return
        ok = await self.cog.chiudi_e_aggiorna(self.sid)
        await interaction.edit_original_response(content=await _testo(interaction, "sb_chiuso_ora" if ok else "sb_gia_chiuso"), view=None)

    @discord.ui.select(cls=discord.ui.RoleSelect, min_values=0, max_values=25, row=0)
    async def ruoli(self, interaction: discord.Interaction, select: discord.ui.RoleSelect) -> None:
        if await self._autorizzato(interaction) is None:
            self.stop()
            await interaction.response.edit_message(content=await _testo(interaction, "sb_non_si_puo"), view=None)
            return
        scelti = [r.id for r in select.values]
        await sondaggi_repo.imposta_ruoli(self.sid, scelti)
        await self.cog.aggiorna_messaggio(self.sid)
        await interaction.response.send_message(
            await _testo(interaction, "sb_ruoli_impostati" if scelti else "sb_ruoli_tolti", n=len(scelti)), ephemeral=True)


async def _testo(interaction: discord.Interaction, chiave: str, **valori) -> str:
    return t(chiave, await lingua_interazione(interaction), **valori)


async def _completa_sondaggi(interaction: discord.Interaction, attuale: str) -> list[app_commands.Choice[str]]:
    """I sondaggi aperti dell'utente (tutti, per chi ha «Gestisci messaggi»), al massimo 25."""
    if interaction.guild is None:
        return []
    staff = interaction.permissions.manage_messages
    trovati = await sondaggi_repo.cerca_domanda(interaction.guild.id, attuale, None if staff else interaction.user.id)
    return [app_commands.Choice(name=f"#{r['id']} {r['domanda']}"[:100], value=str(r["id"])) for r in trovati if r["stato"] != "chiuso"][:25]


_AZIONI_GESTIONE = [
    app_commands.Choice(name="elenco", value="elenco"),
    app_commands.Choice(name="riepilogo", value="riepilogo"),
    app_commands.Choice(name="chiudi", value="chiudi"),
]


async def _completa_gestione(interaction: discord.Interaction, attuale: str) -> list[app_commands.Choice[str]]:
    """Programmati, aperti e chiusi dell'utente (tutti, per chi ha «Gestisci messaggi»), al massimo 25."""
    if interaction.guild is None:
        return []
    staff = interaction.permissions.manage_messages
    trovati = await sondaggi_repo.cerca_domanda(interaction.guild.id, attuale, None if staff else interaction.user.id)
    scelte = [app_commands.Choice(name=f"#{r['id']} {r['domanda']}"[:100], value=str(r["id"])) for r in trovati]
    nativi = await sondaggi_nativi_repo.programmati(interaction.guild.id, None if staff else interaction.user.id, attuale)
    scelte += [app_commands.Choice(name=f"#n{r['id']} {r['domanda']}"[:100], value=f"n{r['id']}") for r in nativi]
    return scelte[:25]


class SondaggiBottoniCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        await super().cog_load()
        self.bot.add_dynamic_items(BottoneSondaggio)
        scheduler.register_handler(AZIONE_CHIUDI, self.alla_scadenza)
        scheduler.register_handler(AZIONE_APRI, self.alla_apertura)

    async def cog_unload(self) -> None:
        self.bot.remove_dynamic_items(BottoneSondaggio)
        await super().cog_unload()

    # --- messaggio ---------------------------------------------------------------------------------------------------
    async def _disegna(self, s) -> tuple[discord.Embed, discord.ui.View]:
        lingua = await lingua_risposta(s["guild_id"], pubblica=True)
        opzioni = await sondaggi_repo.opzioni(s["id"])
        chiuso = s["stato"] == "chiuso"
        risultati = await sondaggi_repo.risultati(s["id"], s["pesato"])
        votanti = await sondaggi_repo.votanti(s["id"]) if not chiuso else sum(v for _, v in risultati)
        return (await embed_sondaggio(s, opzioni, risultati, votanti, lingua, chiuso=chiuso),
                vista_sondaggio(s["id"], opzioni, chiuso=chiuso, lingua=lingua))

    async def aggiorna_messaggio(self, sondaggio_id: int) -> None:
        s = await sondaggi_repo.prendi(sondaggio_id)
        if s is None or not s["message_id"]:
            return
        canale = self.bot.get_channel(s["channel_id"])
        if canale is None:
            return
        embed, vista = await self._disegna(s)
        try:
            await canale.get_partial_message(s["message_id"]).edit(embed=embed, view=vista, allowed_mentions=_NESSUNA_MENZIONE)
        except discord.HTTPException as exc:
            logger.warning("Sondaggio %s: messaggio non aggiornato (%s)", sondaggio_id, exc)

    async def chiudi_e_aggiorna(self, sondaggio_id: int) -> bool:
        if not await sondaggi_repo.chiudi(sondaggio_id):
            return False
        await self.aggiorna_messaggio(sondaggio_id)
        return True

    async def alla_scadenza(self, guild_id: int, user_id: int, payload: dict) -> None:
        """Scheduler: chiude il sondaggio. Se nel frattempo la scadenza è stata spostata, ci pensa l'azione più nuova."""
        s = await sondaggi_repo.prendi(int(payload["id"]))
        if s is None or s["stato"] != "aperto":
            return
        if s["scade_il"] and _aware(s["scade_il"]) > datetime.now(timezone.utc) + timedelta(seconds=5):
            return
        await self.chiudi_e_aggiorna(s["id"])

    async def alla_apertura(self, guild_id: int, user_id: int, payload: dict) -> None:
        """Scheduler: pubblica un sondaggio programmato. Se è stato annullato o già aperto non fa nulla."""
        s = await sondaggi_repo.prendi(int(payload["id"]))
        if s is None or s["stato"] != "programmato":
            return
        canale = self.bot.get_channel(s["channel_id"])
        if canale is None:
            await sondaggi_repo.chiudi(s["id"])
            return
        scade = datetime.now(timezone.utc) + timedelta(seconds=s["durata_s"] or 86400)
        if not await sondaggi_repo.apri(s["id"], scade):
            return
        s = await sondaggi_repo.prendi(s["id"])
        embed, vista = await self._disegna(s)
        try:
            messaggio = await canale.send(embed=embed, view=vista, allowed_mentions=_NESSUNA_MENZIONE)
        except discord.HTTPException as exc:
            logger.warning("Sondaggio %s: non pubblicato (%s)", s["id"], exc)
            await sondaggi_repo.elimina(s["id"])
            return
        await sondaggi_repo.imposta_messaggio(s["id"], messaggio.id)
        await scheduler.schedule(s["guild_id"], s["autore_id"], AZIONE_CHIUDI, scade, {"id": s["id"]})

    # --- bottoni -----------------------------------------------------------------------------------------------------
    async def voto(self, interaction: discord.Interaction, sondaggio_id: int, scelta: int) -> None:
        await interaction.response.defer(ephemeral=True)
        lingua = await lingua_interazione(interaction)
        s = await sondaggi_repo.prendi(sondaggio_id)
        if s is None or interaction.guild is None or s["guild_id"] != interaction.guild.id:
            await interaction.followup.send(t("sb_non_trovato", lingua), ephemeral=True)
            return
        ruoli = {r.id for r in getattr(interaction.user, "roles", [])}
        if not L.puo_votare(ruoli, list(s["ruoli"])):
            await interaction.followup.send(t("sb_ruolo_richiesto", lingua), ephemeral=True)
            return
        peso = L.peso_votante(ruoli, await sondaggi_repo.pesi(s["guild_id"])) if s["pesato"] else 1
        esito, scelte, votanti = await sondaggi_repo.vota(sondaggio_id, interaction.user.id, scelta, peso, datetime.now(timezone.utc))
        if esito in ("chiuso", "senza_opzione"):
            await interaction.followup.send(t("sb_opzione_tolta" if esito == "senza_opzione" else "sb_gia_chiuso", lingua),
                                            ephemeral=True)
            return
        if esito == "uguale":
            await interaction.followup.send(t("sb_gia_votato", lingua), ephemeral=True)
            return
        elenco = ", ".join(str(n + 1) for n in sorted(scelte)) or "-"
        await interaction.followup.send(t("sb_voto_registrato", lingua, scelte=elenco), ephemeral=True)
        if s["chiudi_a_voti"] and votanti >= s["chiudi_a_voti"]:
            await self.chiudi_e_aggiorna(sondaggio_id)
        elif s["risultati"] == "subito":
            await self.aggiorna_messaggio(sondaggio_id)

    async def togli_voto(self, interaction: discord.Interaction, sondaggio_id: int) -> None:
        await interaction.response.defer(ephemeral=True)
        lingua = await lingua_interazione(interaction)
        tolto = await sondaggi_repo.togli_voto(sondaggio_id, interaction.user.id)
        await interaction.followup.send(t("sb_voto_tolto" if tolto else "sb_niente_da_togliere", lingua), ephemeral=True)
        if tolto:
            s = await sondaggi_repo.prendi(sondaggio_id)
            if s is not None and s["risultati"] == "subito":
                await self.aggiorna_messaggio(sondaggio_id)

    async def mostra_risultati(self, interaction: discord.Interaction, sondaggio_id: int) -> None:
        await interaction.response.defer(ephemeral=True)
        lingua = await lingua_interazione(interaction)
        s = await sondaggi_repo.prendi(sondaggio_id)
        if s is None:
            await interaction.followup.send(t("sb_non_trovato", lingua), ephemeral=True)
            return
        chiuso = s["stato"] == "chiuso"
        if not chiuso and s["risultati"] == "alla_fine":
            await interaction.followup.send(t("sb_risultati_nascosti_n", lingua, votanti=await sondaggi_repo.votanti(sondaggio_id)),
                                            ephemeral=True)
            return
        risultati = await sondaggi_repo.risultati(sondaggio_id, s["pesato"])
        righe = L.righe_risultati(risultati)
        if not s["anonimo"] and not chiuso:
            chi = await sondaggi_repo.votanti_per_opzione(sondaggio_id)
            for n in range(len(righe)):
                utenti = chi.get(n, [])
                if utenti:
                    resto = len(utenti) - 10
                    righe[n] += "\n" + " ".join(f"<@{u}>" for u in utenti[:10]) + (f" +{resto}" if resto > 0 else "")
        await interaction.followup.send("\n\n".join(righe)[:2000], ephemeral=True, allowed_mentions=_NESSUNA_MENZIONE)

    async def apri_gestione(self, interaction: discord.Interaction, sondaggio_id: int) -> None:
        lingua = await lingua_interazione(interaction)
        s = await sondaggi_repo.prendi(sondaggio_id)
        if s is None or s["stato"] != "aperto":
            await interaction.response.send_message(t("sb_gia_chiuso", lingua), ephemeral=True)
            return
        if not puo_gestire(interaction, s["autore_id"]):
            await interaction.response.send_message(t("sb_non_si_puo", lingua), ephemeral=True)
            return
        vista = GestioneSondaggio(self, interaction.user.id, sondaggio_id, (t("sb_chiudi_ora", lingua), t("sb_scegli_ruoli", lingua)))
        await interaction.response.send_message(t("sb_gestione", lingua), view=vista, ephemeral=True)

    # --- /sondaggi bottoni -------------------------------------------------------------------------------------------
    @comando_di_gruppo("sondaggi", nome="bottoni", descrizione="Crea un sondaggio a bottoni (fino a 20 opzioni).")
    @app_commands.describe(
        domanda="La domanda (massimo 256 caratteri)",
        opzioni="Le opzioni separate da | (da 2 a 20, massimo 80 caratteri l'una)",
        durata="Quanto dura: 30m, 12h, 7d (massimo 30d; di base 24h)",
        anonimo="Nessuno vede chi ha votato, nemmeno lo staff",
        risultati="Quando si vedono i risultati",
        multipla="Si può votare più di un'opzione",
        ruolo="Può votare solo chi ha questo ruolo (altri ruoli da «Gestisci»)",
        pesato="Il voto vale il peso del ruolo (lo decide lo staff)",
        chiudi_a_voti="Si chiude da solo quando hanno votato tante persone",
        canale="Dove pubblicarlo (di base questo canale)",
        inizia_tra="Si pubblica più tardi: 30m, 12h, 7d (da 1 minuto a 30 giorni)",
    )
    @app_commands.choices(risultati=_RISULTATI)
    async def bottoni(
        self, interaction: discord.Interaction, domanda: app_commands.Range[str, 1, L.MAX_DOMANDA],
        opzioni: app_commands.Range[str, 3, 1700], durata: app_commands.Range[str, 2, 6] = "24h", anonimo: bool = False,
        risultati: str = "subito", multipla: bool = False, ruolo: discord.Role | None = None, pesato: bool = False,
        chiudi_a_voti: app_commands.Range[int, 1, L.MAX_VOTANTI_CHIUSURA] | None = None,
        canale: discord.TextChannel | None = None, inizia_tra: app_commands.Range[str, 2, 6] | None = None,
    ) -> None:
        guild = interaction.guild
        lingua = await lingua_interazione(interaction)
        if guild is None:
            await interaction.response.send_message(t("guild_only_command", lingua), ephemeral=True)
            return
        if not await db.is_module_active_for_guild(guild.id, MODULE_POLL):
            await interaction.response.send_message(t("ping_questo_modulo_non_attivo_su", lingua), ephemeral=True)
            return
        lette = L.leggi_opzioni(opzioni)
        if isinstance(lette, str):
            await interaction.response.send_message(t(f"sb_opzioni_{lette}", lingua, massimo=L.MAX_OPZIONI), ephemeral=True)
            return
        try:
            secondi = parse_duration(durata)
        except ValueError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return
        if not DURATA_MINIMA <= secondi <= DURATA_MASSIMA:
            await interaction.response.send_message(t("sb_durata_fuori", lingua), ephemeral=True)
            return
        attesa = 0
        if inizia_tra:
            try:
                attesa = parse_duration(inizia_tra)
            except ValueError as exc:
                await interaction.response.send_message(str(exc), ephemeral=True)
                return
            if not L.inizio_valido(attesa):
                await interaction.response.send_message(t("sb_inizio_fuori", lingua), ephemeral=True)
                return
        dove = canale or interaction.channel
        mio = dove.permissions_for(guild.me)
        suo = dove.permissions_for(interaction.user)
        if not (mio.view_channel and mio.send_messages and mio.embed_links and suo.send_messages):
            await interaction.response.send_message(t("sb_canale_non_ammesso", lingua), ephemeral=True)
            return
        if len(await sondaggi_repo.elenco(guild.id, interaction.user.id, "aperto", MAX_APERTI_PER_AUTORE)) >= MAX_APERTI_PER_AUTORE:
            await interaction.response.send_message(t("sb_troppi_aperti", lingua, massimo=MAX_APERTI_PER_AUTORE), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        if attesa:
            inizio = datetime.now(timezone.utc) + timedelta(seconds=attesa)
            sid = await sondaggi_repo.crea(
                guild.id, dove.id, interaction.user.id, domanda, lette, anonimo=anonimo, risultati=risultati, multipla=multipla,
                pesato=pesato, ruoli=[ruolo.id] if ruolo else [], chiudi_a_voti=chiudi_a_voti, inizia_il=inizio, durata_s=secondi,
                stato="programmato",
            )
            await scheduler.schedule(guild.id, interaction.user.id, AZIONE_APRI, inizio, {"id": sid})
            await interaction.followup.send(
                t("sb_programmato", lingua, quando=discord.utils.format_dt(inizio, "R"), id=sid), ephemeral=True)
            return
        scade = datetime.now(timezone.utc) + timedelta(seconds=secondi)
        sid = await sondaggi_repo.crea(
            guild.id, dove.id, interaction.user.id, domanda, lette, anonimo=anonimo, risultati=risultati, multipla=multipla,
            pesato=pesato, ruoli=[ruolo.id] if ruolo else [], chiudi_a_voti=chiudi_a_voti, scade_il=scade, durata_s=secondi,
        )
        s = await sondaggi_repo.prendi(sid)
        embed, vista = await self._disegna(s)
        try:
            messaggio = await dove.send(embed=embed, view=vista, allowed_mentions=_NESSUNA_MENZIONE)
        except discord.HTTPException:
            await sondaggi_repo.elimina(sid)
            await interaction.followup.send(t("sb_non_pubblicato", lingua), ephemeral=True)
            return
        await sondaggi_repo.imposta_messaggio(sid, messaggio.id)
        await scheduler.schedule(guild.id, interaction.user.id, AZIONE_CHIUDI, scade, {"id": sid})
        await interaction.followup.send(t("sb_creato", lingua, link=messaggio.jump_url), ephemeral=True)

    # --- /sondaggi modifica ------------------------------------------------------------------------------------------
    @comando_di_gruppo("sondaggi", nome="modifica", descrizione="Cambia domanda, opzioni o durata di un sondaggio a bottoni aperto.")
    @app_commands.describe(sondaggio="Il sondaggio da cambiare (scegli dall'elenco)")
    @app_commands.autocomplete(sondaggio=_completa_sondaggi)
    async def modifica(self, interaction: discord.Interaction, sondaggio: app_commands.Range[str, 1, 20]) -> None:
        lingua = await lingua_interazione(interaction)
        s = await sondaggi_repo.prendi(int(sondaggio)) if sondaggio.isdigit() else None
        if s is None or interaction.guild is None or s["guild_id"] != interaction.guild.id or s["stato"] != "aperto":
            await interaction.response.send_message(t("sb_non_trovato", lingua), ephemeral=True)
            return
        if not puo_gestire(interaction, s["autore_id"]):
            await interaction.response.send_message(t("sb_non_si_puo", lingua), ephemeral=True)
            return
        await interaction.response.send_modal(ModaleModifica(self, s, await sondaggi_repo.opzioni(s["id"]), lingua))

    async def applica_modifica(self, interaction: discord.Interaction, sid: int, domanda: str, opzioni_testo: str, durata: str) -> None:
        lingua = await lingua_interazione(interaction)
        s = await sondaggi_repo.prendi(sid)
        if s is None or s["stato"] != "aperto" or not puo_gestire(interaction, s["autore_id"]):
            await interaction.response.send_message(t("sb_non_si_puo", lingua), ephemeral=True)
            return
        lette = L.leggi_opzioni(opzioni_testo.replace("\n", "|"))
        if isinstance(lette, str):
            await interaction.response.send_message(t(f"sb_opzioni_{lette}", lingua, massimo=L.MAX_OPZIONI), ephemeral=True)
            return
        scade = None
        if durata.strip():
            try:
                secondi = parse_duration(durata)
            except ValueError as exc:
                await interaction.response.send_message(str(exc), ephemeral=True)
                return
            if not DURATA_MINIMA <= secondi <= DURATA_MASSIMA:
                await interaction.response.send_message(t("sb_durata_fuori", lingua), ephemeral=True)
                return
            scade = datetime.now(timezone.utc) + timedelta(seconds=secondi)
        vecchie = await sondaggi_repo.risultati(sid, False)
        nuove = {o.casefold() for o in lette}
        perse = [(o, v) for o, v in vecchie if o.casefold() not in nuove and v > 0]
        if perse:
            vista = ConfermaModifica(self, interaction.user.id, sid, domanda.strip()[: L.MAX_DOMANDA], lette, scade,
                                     (t("sb_conferma", lingua), t("sb_annulla", lingua)))
            elenco = ", ".join(o[:30] for o, _ in perse[:5])
            await interaction.response.send_message(t("sb_conferma_toglie", lingua, opzioni=elenco, voti=sum(v for _, v in perse)),
                                                    view=vista, ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        esito = await self.scrivi_modifica(sid, domanda.strip()[: L.MAX_DOMANDA], lette, scade)
        await interaction.followup.send(t(esito, lingua), ephemeral=True)

    async def scrivi_modifica(self, sid: int, domanda: str, opzioni: list[str], scade: datetime | None) -> str:
        persi = await sondaggi_repo.modifica(sid, domanda, opzioni, scade)
        if persi is None:
            return "sb_gia_chiuso"
        if scade is not None:
            s = await sondaggi_repo.prendi(sid)
            await scheduler.schedule(s["guild_id"], s["autore_id"], AZIONE_CHIUDI, scade, {"id": sid})
        await self.aggiorna_messaggio(sid)
        return "sb_modificato"

    # --- /sondaggi gestisci ------------------------------------------------------------------------------------------
    @comando_di_gruppo("sondaggi", nome="gestisci", descrizione="Elenco, riepilogo o chiusura dei sondaggi a bottoni.")
    @app_commands.describe(azione="Cosa fare", sondaggio="Il sondaggio (serve per riepilogo e chiudi)")
    @app_commands.choices(azione=_AZIONI_GESTIONE)
    @app_commands.autocomplete(sondaggio=_completa_gestione)
    async def gestisci(self, interaction: discord.Interaction, azione: str,
                       sondaggio: app_commands.Range[str, 1, 20] | None = None) -> None:
        lingua = await lingua_interazione(interaction)
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(t("guild_only_command", lingua), ephemeral=True)
            return
        if azione == "elenco":
            staff = interaction.permissions.manage_messages
            autore = None if staff else interaction.user.id
            righe = await sondaggi_repo.elenco_gestione(guild.id, autore)
            nativi = await sondaggi_nativi_repo.programmati(guild.id, autore)
            corpo = "\n".join(
                [f"#{r['id']} · {t('sb_stato_' + r['stato'], lingua)} · {r['domanda'][:80]}" for r in righe]
                + [f"#n{r['id']} · {t('sb_stato_programmato', lingua)} · {r['domanda'][:80]}" for r in nativi])
            await interaction.response.send_message(corpo[:1900] or t("sb_elenco_vuoto", lingua), ephemeral=True,
                                                    allowed_mentions=_NESSUNA_MENZIONE)
            return
        if sondaggio and sondaggio[0] in "nN":
            await self._gestisci_nativo(interaction, azione, sondaggio[1:], lingua)
            return
        s = await sondaggi_repo.prendi(int(sondaggio)) if sondaggio and sondaggio.isdigit() else None
        if s is None or s["guild_id"] != guild.id:
            await interaction.response.send_message(t("sb_non_trovato", lingua), ephemeral=True)
            return
        if not puo_gestire(interaction, s["autore_id"]):
            await interaction.response.send_message(t("sb_non_si_puo", lingua), ephemeral=True)
            return
        if azione == "chiudi":
            await interaction.response.defer(ephemeral=True)
            ok = await self.chiudi_e_aggiorna(s["id"])
            await interaction.followup.send(t("sb_chiuso_ora" if ok else "sb_gia_chiuso", lingua), ephemeral=True)
            return
        await interaction.response.send_message(await self._riepilogo(s, lingua), ephemeral=True,
                                                allowed_mentions=_NESSUNA_MENZIONE)

    async def _gestisci_nativo(self, interaction: discord.Interaction, azione: str, chiave: str, lingua: str) -> None:
        """Sondaggio nativo programmato («n12»): si vede e si annulla finché non è partito."""
        r = await sondaggi_nativi_repo.prendi(int(chiave)) if chiave.isdigit() else None
        if r is None or r["guild_id"] != interaction.guild.id or r["stato"] != "programmato":
            await interaction.response.send_message(t("sb_non_trovato", lingua), ephemeral=True)
            return
        if not puo_gestire(interaction, r["autore_id"]):
            await interaction.response.send_message(t("sb_non_si_puo", lingua), ephemeral=True)
            return
        if azione == "chiudi":
            ok = await sondaggi_nativi_repo.annulla_programmato(r["id"])
            await interaction.response.send_message(t("sb_nativo_annullato" if ok else "sb_non_trovato", lingua), ephemeral=True)
            return
        corpo = (f"**#n{r['id']}** {r['domanda'][:200]}\n{t('sb_stato_programmato', lingua)}\n"
                 + t("sb_inizia", lingua, quando=discord.utils.format_dt(_aware(r["inizia_il"]), "R")))
        await interaction.response.send_message(corpo[:1900], ephemeral=True, allowed_mentions=_NESSUNA_MENZIONE)

    async def _riepilogo(self, s, lingua: str) -> str:
        chiuso = s["stato"] == "chiuso"
        intestazione = f"**#{s['id']}** {s['domanda'][:200]}\n{t('sb_stato_' + s['stato'], lingua)}"
        if s["stato"] == "programmato":
            return intestazione + "\n" + t("sb_inizia", lingua, quando=discord.utils.format_dt(_aware(s["inizia_il"]), "R"))
        risultati = await sondaggi_repo.risultati(s["id"], s["pesato"])
        votanti = sum(v for _, v in risultati) if chiuso else await sondaggi_repo.votanti(s["id"])
        corpo = intestazione + "\n" + t("sb_votanti", lingua, votanti=votanti)
        if chiuso or s["risultati"] == "subito":
            corpo += "\n\n" + "\n\n".join(L.righe_risultati(risultati))
        return corpo[:1900]

    # --- /admin-moduli sondaggi --------------------------------------------------------------------------------------
    @comando_di_gruppo("admin-moduli", nome="pesi", descrizione="Dai un peso al voto di un ruolo nei sondaggi (max 25 ruoli).", sottogruppo=_SG_ADMIN)
    @app_commands.describe(azione="Cosa fare", ruolo="Il ruolo (serve per imposta e togli)",
                           peso="Quanto vale il voto di chi ha il ruolo, da 1 a 100")
    @app_commands.choices(azione=_AZIONI_PESO)
    async def pesi(self, interaction: discord.Interaction, azione: str, ruolo: discord.Role | None = None,
                   peso: app_commands.Range[int, 1, L.PESO_MASSIMO] | None = None) -> None:
        lingua = await lingua_interazione(interaction)
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(t("guild_only_command", lingua), ephemeral=True)
            return
        if azione == "elenco":
            pesi = await sondaggi_repo.pesi(guild.id)
            righe = [f"<@&{r}> = {p}" for r, p in sorted(pesi.items(), key=lambda x: -x[1])]
            await interaction.response.send_message("\n".join(righe)[:1900] or t("sb_pesi_nessuno", lingua), ephemeral=True,
                                                    allowed_mentions=_NESSUNA_MENZIONE)
            return
        if ruolo is None or (azione == "imposta" and peso is None):
            await interaction.response.send_message(t("sb_pesi_manca", lingua), ephemeral=True)
            return
        if azione == "togli":
            ok = await sondaggi_repo.togli_peso(guild.id, ruolo.id)
            await interaction.response.send_message(t("sb_peso_tolto" if ok else "sb_peso_assente", lingua), ephemeral=True)
            return
        esito = await sondaggi_repo.imposta_peso(guild.id, ruolo.id, peso)
        await interaction.response.send_message(
            t("sb_peso_impostato" if esito == "ok" else "sb_pesi_pieno", lingua, ruolo=ruolo.name, peso=peso, massimo=L.MAX_PESI),
            ephemeral=True)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> None:
        """Un canale cancellato porta via i suoi sondaggi (opzioni e voti a cascata)."""
        try:
            await sondaggi_repo.elimina_del_canale(channel.guild.id, channel.id)
        except Exception:
            logger.exception("Sondaggi: pulizia del canale %s fallita", channel.id)

    # --- chi esce perde il voto -------------------------------------------------------------------------------------
    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        if not member.bot:
            await sondaggi_repo.togli_voti_utente(member.guild.id, member.id)

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.abc.User) -> None:
        if not user.bot:
            await sondaggi_repo.togli_voti_utente(guild.id, user.id)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(SondaggiBottoniCog(bot))
