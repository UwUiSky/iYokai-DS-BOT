"""
cogs/utility/ruoli_strumenti.py
===============================
Strumenti sui ruoli. Per lo staff, il gruppo `/ruoli`: dare e togliere
ruoli a un membro (anche a tempo), togliergli tutto, operazioni di massa
con stima, stop e avviso finale, creare e modificare un ruolo, diagnosi,
ruoli a scelta. Per tutti, `/utility ruolo`: prendere e lasciare i ruoli
a scelta. La logica è in core/ruoli_strumenti_logic.py.
Funzioni coperte: SPEC §14 (catalogo #123: RUO-042, 043, 090-109, 113)
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

import discord
from discord import app_commands
from discord.ext import commands

from core.command_access import Livello, autocomplete_protetto
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.duration_logic import format_duration, parse_duration
from core.lista_limiti_logic import righe_entro_limite
from core.repositories.self_role_repo import self_role_repo
from core.role_safety import check_role_assignable
from core.ruoli_strumenti_logic import (
    AZIONE_DAI,
    AZIONE_TOGLI,
    CHI_BOT,
    CHI_TUTTI,
    CHI_UMANI,
    MAX_DURATA_TEMPORANEO,
    MAX_MEMBRI_MASSA,
    MAX_RUOLI_SCELTA,
    MAX_RUOLI_SERVER,
    PAUSA_MASSA_SECONDI,
    RUOLI_TEMPORANEI_ACTION_TYPE,
    FiltroMassa,
    colore_ruolo,
    diagnosi_ruolo,
    leggi_data,
    membri_da_toccare,
    ripristino,
    ruoli_da_azzerare,
    ruoli_unici,
    stima_secondi,
    stima_in_parole,
)
from core.scheduler import in_seconds, scheduler
from core.ui_base import BaseView

logger = logging.getLogger("iyokai.ruoli_strumenti")

NESSUNA_MENZIONE = discord.AllowedMentions.none()
# Dopo tanti errori di fila l'operazione di massa si ferma: il ruolo è sparito o il bot ha perso i permessi.
MAX_ERRORI_DI_FILA = 10
SCELTE_AZIONE = [
    app_commands.Choice(name="dai", value=AZIONE_DAI),
    app_commands.Choice(name="togli", value=AZIONE_TOGLI),
]


def motivo_audit(autore, motivo: str | None) -> str:
    """Il motivo per il registro di Discord, entro 512 caratteri."""
    return f"{motivo or 'Nessun motivo'} — da {autore} ({autore.id})"[:512]


def gestibile_dal_bot(guild: discord.Guild, ruolo) -> bool:
    """Il bot può dare o togliere il ruolo: non è @everyone, non è gestito, sta sotto il bot."""
    return ruolo is not None and not ruolo.is_default() and not ruolo.managed and ruolo < guild.me.top_role


@dataclass
class OperazioneMassa:
    azione: str
    ruolo_id: int
    totale: int
    autore_id: int
    fatti: int = 0
    falliti: int = 0
    ferma: bool = False
    task: asyncio.Task | None = field(default=None, repr=False)


class ConfermaAzzera(BaseView):
    """Conferma prima di togliere tutti i ruoli; poi un bottone per ridarli (15 minuti)."""

    def __init__(self, cog: "RuoliStrumentiCog", autore_id: int, membro: discord.Member, motivo: str | None) -> None:
        super().__init__(timeout=900)
        self.cog = cog
        self.autore_id = autore_id
        self.membro = membro
        self.motivo = motivo
        self.tolti: list[discord.Role] = []

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.autore_id:
            await interaction.response.send_message("Solo chi ha lanciato il comando può usare questi bottoni.", ephemeral=True)
            return False
        return await super().interaction_check(interaction)

    @discord.ui.button(label="Togli tutti i ruoli", style=discord.ButtonStyle.danger)
    async def conferma(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        guild = interaction.guild
        ruoli = ruoli_da_azzerare(self.membro.roles, guild.me.top_role)
        if not ruoli:
            await interaction.response.edit_message(content="Non c'è nessun ruolo che il bot possa togliere.", view=None)
            return
        try:
            await self.membro.remove_roles(*ruoli, reason=motivo_audit(interaction.user, self.motivo))
        except discord.HTTPException as errore:
            await interaction.response.edit_message(content=f"Discord ha rifiutato: {errore.text or errore}"[:1900], view=None)
            return
        self.tolti = ruoli
        button.disabled = True
        self.ridai.disabled = False
        elenco = ", ".join(r.mention for r in ruoli)
        testo, _ = righe_entro_limite([f"Tolti a {self.membro.mention}: {elenco}"], 1800)
        await interaction.response.edit_message(
            content=testo + "\nPuoi ridarli entro 15 minuti con il bottone.", view=self, allowed_mentions=NESSUNA_MENZIONE
        )

    @discord.ui.button(label="Ridai i ruoli", style=discord.ButtonStyle.secondary, disabled=True)
    async def ridai(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        guild = interaction.guild
        ruoli = [r for r in self.tolti if gestibile_dal_bot(guild, guild.get_role(r.id))]
        try:
            if ruoli:
                await self.membro.add_roles(*ruoli, reason=motivo_audit(interaction.user, "Ruoli ridati dopo l'azzeramento"))
        except discord.HTTPException as errore:
            await interaction.response.edit_message(content=f"Discord ha rifiutato: {errore.text or errore}"[:1900], view=None)
            return
        self.stop()
        await interaction.response.edit_message(
            content=f"Ridati {len(ruoli)} ruoli a {self.membro.mention}.", view=None, allowed_mentions=NESSUNA_MENZIONE
        )


class SceltaRuoliView(BaseView):
    """Tendina con i ruoli a scelta: quelli segnati restano o arrivano, gli altri si lasciano."""

    def __init__(self, cog: "RuoliStrumentiCog", membro: discord.Member, ruoli: list[discord.Role]) -> None:
        super().__init__(timeout=300)
        self.cog = cog
        self.membro_id = membro.id
        posseduti = {r.id for r in membro.roles}
        opzioni = [
            discord.SelectOption(label=r.name[:100], value=str(r.id), default=r.id in posseduti)
            for r in ruoli[:MAX_RUOLI_SCELTA]
        ]
        self.menu = discord.ui.Select(
            placeholder="Scegli i tuoi ruoli", min_values=0, max_values=len(opzioni), options=opzioni
        )
        self.menu.callback = self._scelto
        self.add_item(self.menu)

    async def _scelto(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.membro_id:
            await interaction.response.send_message("Questo menu non è tuo: usa /utility ruolo.", ephemeral=True)
            return
        scelti = {int(v) for v in self.menu.values}
        offerti = {int(o.value) for o in self.menu.options}
        testo = await self.cog.applica_scelta(interaction.user, scelti, offerti - scelti)
        await interaction.response.edit_message(content=testo, view=None, allowed_mentions=NESSUNA_MENZIONE)
        self.stop()


class RuoliStrumentiCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.operazioni: dict[int, OperazioneMassa] = {}

    async def cog_unload(self) -> None:
        for operazione in self.operazioni.values():
            operazione.ferma = True
        await super().cog_unload()

    # ================================================================
    # Controlli comuni
    # ================================================================
    @staticmethod
    async def _rifiuta(interaction: discord.Interaction, testo: str) -> None:
        if interaction.response.is_done():
            await interaction.followup.send(testo, ephemeral=True, allowed_mentions=NESSUNA_MENZIONE)
        else:
            await interaction.response.send_message(testo, ephemeral=True, allowed_mentions=NESSUNA_MENZIONE)

    @staticmethod
    def _primo_problema(guild, ruoli, autore, *, self_service: bool = False) -> str | None:
        for ruolo in ruoli:
            motivo = check_role_assignable(guild, ruolo, autore, self_service=self_service)
            if motivo is not None:
                return f"{ruolo.mention}: {motivo}"
        return None

    @staticmethod
    def _durata(testo: str | None) -> int | None:
        """Secondi della durata, None se non data. ValueError se scritta male o troppo lunga."""
        if testo is None or not testo.strip():
            return None
        secondi = parse_duration(testo)
        if secondi > MAX_DURATA_TEMPORANEO:
            raise ValueError("Un cambio a tempo dura al massimo 30 giorni.")
        return secondi

    # ================================================================
    # Dai / togli (anche a tempo)
    # ================================================================
    async def _cambia(
        self,
        interaction: discord.Interaction,
        membro: discord.Member,
        ruoli: list,
        azione: str,
        durata: str | None,
        motivo: str | None,
    ) -> None:
        guild = interaction.guild
        try:
            secondi = self._durata(durata)
        except ValueError as errore:
            await self._rifiuta(interaction, str(errore))
            return
        ruoli = ruoli_unici(ruoli)
        problema = self._primo_problema(guild, ruoli, interaction.user)
        if problema is not None:
            await self._rifiuta(interaction, problema)
            return
        posseduti = {r.id for r in membro.roles}
        if azione == AZIONE_DAI:
            da_cambiare = [r for r in ruoli if r.id not in posseduti]
        else:
            da_cambiare = [r for r in ruoli if r.id in posseduti]
        if not da_cambiare:
            await self._rifiuta(interaction, "Non c'è niente da cambiare: il membro è già così.")
            return
        await interaction.response.defer(ephemeral=True)
        try:
            if azione == AZIONE_DAI:
                await membro.add_roles(*da_cambiare, reason=motivo_audit(interaction.user, motivo))
            else:
                await membro.remove_roles(*da_cambiare, reason=motivo_audit(interaction.user, motivo))
        except discord.HTTPException as errore:
            await interaction.followup.send(f"Discord ha rifiutato: {errore.text or errore}"[:1900], ephemeral=True)
            return
        ids = [r.id for r in da_cambiare]
        elenco = ", ".join(r.mention for r in da_cambiare)
        verbo = "Dati" if azione == AZIONE_DAI else "Tolti"
        testo = f"{verbo} a {membro.mention}: {elenco}."
        if secondi is not None:
            payload = {"dati": ids if azione == AZIONE_DAI else [], "tolti": ids if azione == AZIONE_TOGLI else []}
            await scheduler.schedule(guild.id, membro.id, RUOLI_TEMPORANEI_ACTION_TYPE, in_seconds(secondi), payload)
            testo += f" Tra {format_duration(secondi)} torna tutto com'era."
        await interaction.followup.send(testo[:1900], ephemeral=True, allowed_mentions=NESSUNA_MENZIONE)

    async def handle_ruoli_temporanei(self, guild_id: int, user_id: int, payload: dict) -> None:
        """Handler dello scheduler: a fine tempo toglie i ruoli dati e ridà quelli tolti."""
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            return
        membro = guild.get_member(user_id)
        if membro is None:
            return
        da_togliere, da_ridare = ripristino(
            payload.get("dati", []), payload.get("tolti", []), {r.id for r in membro.roles}
        )
        togli = [guild.get_role(r) for r in da_togliere if gestibile_dal_bot(guild, guild.get_role(r))]
        ridai = [guild.get_role(r) for r in da_ridare if gestibile_dal_bot(guild, guild.get_role(r))]
        motivo = "Fine del cambio di ruoli a tempo"
        try:
            if togli:
                await membro.remove_roles(*togli, reason=motivo)
            if ridai:
                await membro.add_roles(*ridai, reason=motivo)
        except discord.NotFound:
            return  # il membro è uscito nel frattempo
        # Gli altri errori risalgono: lo scheduler ritenta più tardi.

    @comando_di_gruppo("ruoli", nome="dai", descrizione="Dai uno o più ruoli a un membro, anche per un tempo.")
    @app_commands.describe(
        membro="A chi dare i ruoli",
        ruolo="Il ruolo da dare",
        ruolo2="Un secondo ruolo",
        ruolo3="Un terzo ruolo",
        durata="Per quanto tempo, es. 2h o 7d (vuoto = per sempre, al massimo 30d)",
        motivo="Il motivo, finisce nel registro di Discord",
    )
    async def dai(
        self,
        interaction: discord.Interaction,
        membro: discord.Member,
        ruolo: discord.Role,
        ruolo2: discord.Role | None = None,
        ruolo3: discord.Role | None = None,
        durata: app_commands.Range[str, 2, 10] | None = None,
        motivo: app_commands.Range[str, 1, 400] | None = None,
    ) -> None:
        await self._cambia(interaction, membro, [ruolo, ruolo2, ruolo3], AZIONE_DAI, durata, motivo)

    @comando_di_gruppo("ruoli", nome="togli", descrizione="Togli uno o più ruoli a un membro, anche per un tempo.")
    @app_commands.describe(
        membro="A chi togliere i ruoli",
        ruolo="Il ruolo da togliere",
        ruolo2="Un secondo ruolo",
        ruolo3="Un terzo ruolo",
        durata="Per quanto tempo, es. 2h o 7d (vuoto = per sempre, al massimo 30d)",
        motivo="Il motivo, finisce nel registro di Discord",
    )
    async def togli(
        self,
        interaction: discord.Interaction,
        membro: discord.Member,
        ruolo: discord.Role,
        ruolo2: discord.Role | None = None,
        ruolo3: discord.Role | None = None,
        durata: app_commands.Range[str, 2, 10] | None = None,
        motivo: app_commands.Range[str, 1, 400] | None = None,
    ) -> None:
        await self._cambia(interaction, membro, [ruolo, ruolo2, ruolo3], AZIONE_TOGLI, durata, motivo)

    @comando_di_gruppo("ruoli", nome="azzera", descrizione="Togli tutti i ruoli a un membro, con conferma.")
    @app_commands.describe(membro="A chi togliere tutti i ruoli", motivo="Il motivo, finisce nel registro di Discord")
    async def azzera(
        self,
        interaction: discord.Interaction,
        membro: discord.Member,
        motivo: app_commands.Range[str, 1, 400] | None = None,
    ) -> None:
        guild = interaction.guild
        if interaction.user.id != guild.owner_id and membro.top_role >= interaction.user.top_role:
            await self._rifiuta(interaction, "Questo membro è pari o sopra di te: non puoi togliergli i ruoli.")
            return
        ruoli = ruoli_da_azzerare(membro.roles, guild.me.top_role)
        if not ruoli:
            await self._rifiuta(interaction, "Non c'è nessun ruolo che il bot possa togliere a questo membro.")
            return
        vista = ConfermaAzzera(self, interaction.user.id, membro, motivo)
        await interaction.response.send_message(
            f"Togliere {len(ruoli)} ruoli a {membro.mention}?", view=vista, ephemeral=True, allowed_mentions=NESSUNA_MENZIONE
        )

    # ================================================================
    # Operazioni di massa
    # ================================================================
    @comando_di_gruppo("ruoli", nome="massa", descrizione="Dai o togli un ruolo a molti membri insieme, con filtri.")
    @app_commands.describe(
        azione="Dare o togliere",
        ruolo="Il ruolo",
        chi="Tutti, solo gli umani o solo i bot",
        con_ruolo="Solo chi ha questo ruolo",
        senza_ruolo="Solo chi non ha questo ruolo",
        entrati_dopo="Solo chi è entrato da questa data (AAAA-MM-GG)",
        entrati_prima="Solo chi è entrato prima di questa data (AAAA-MM-GG)",
        canale_avviso="Dove scrivere a fine lavoro (vuoto = qui)",
    )
    @app_commands.choices(
        azione=SCELTE_AZIONE,
        chi=[
            app_commands.Choice(name="tutti", value=CHI_TUTTI),
            app_commands.Choice(name="umani", value=CHI_UMANI),
            app_commands.Choice(name="bot", value=CHI_BOT),
        ],
    )
    async def massa(
        self,
        interaction: discord.Interaction,
        azione: str,
        ruolo: discord.Role,
        chi: str = CHI_TUTTI,
        con_ruolo: discord.Role | None = None,
        senza_ruolo: discord.Role | None = None,
        entrati_dopo: app_commands.Range[str, 10, 10] | None = None,
        entrati_prima: app_commands.Range[str, 10, 10] | None = None,
        canale_avviso: discord.TextChannel | None = None,
    ) -> None:
        guild = interaction.guild
        if guild.id in self.operazioni:
            await self._rifiuta(interaction, "C'è già un'operazione di massa in corso: aspetta o fermala con /ruoli massa-ferma.")
            return
        try:
            filtro = FiltroMassa(
                chi=chi,
                con_ruolo=con_ruolo.id if con_ruolo else None,
                senza_ruolo=senza_ruolo.id if senza_ruolo else None,
                entrati_dopo=leggi_data(entrati_dopo),
                entrati_prima=leggi_data(entrati_prima),
            )
        except ValueError as errore:
            await self._rifiuta(interaction, str(errore))
            return
        # Dare a tutti un ruolo con permessi forti è un rischio: si accetta solo a mano, membro per membro.
        problema = self._primo_problema(guild, [ruolo], interaction.user, self_service=azione == AZIONE_DAI)
        if problema is not None:
            await self._rifiuta(interaction, problema)
            return
        # Il posto si prenota prima del primo await: due comandi insieme non partono entrambi.
        operazione = OperazioneMassa(azione, ruolo.id, 0, interaction.user.id)
        self.operazioni[guild.id] = operazione
        try:
            await interaction.response.defer(ephemeral=True)
            if not guild.chunked:
                await guild.chunk()
            membri = membri_da_toccare(guild.members, filtro, ruolo.id, azione)
            if not membri:
                self.operazioni.pop(guild.id, None)
                await interaction.followup.send("Nessun membro da cambiare con questi filtri.", ephemeral=True)
                return
            if len(membri) > MAX_MEMBRI_MASSA:
                self.operazioni.pop(guild.id, None)
                await interaction.followup.send(
                    f"Sono {len(membri)} membri: il massimo per un'operazione è {MAX_MEMBRI_MASSA}. Usa i filtri per dividerla.",
                    ephemeral=True,
                )
                return
        except BaseException:
            self.operazioni.pop(guild.id, None)
            raise
        canale = canale_avviso or interaction.channel
        operazione.totale = len(membri)
        operazione.task = asyncio.create_task(
            self._esegui_massa(guild, ruolo, membri, operazione, canale, motivo_audit(interaction.user, "Operazione di massa"))
        )
        verbo = "dare" if azione == AZIONE_DAI else "togliere"
        await interaction.followup.send(
            f"Avviata: {verbo} {ruolo.mention} a {len(membri)} membri, {stima_in_parole(stima_secondi(len(membri)))}. "
            f"Avviso finale in {getattr(canale, 'mention', 'questo canale')}. Per fermarla: /ruoli massa-ferma.",
            ephemeral=True,
            allowed_mentions=NESSUNA_MENZIONE,
        )

    async def _esegui_massa(self, guild, ruolo, membri, operazione: OperazioneMassa, canale, motivo: str) -> None:
        errori_di_fila = 0
        interrotta = None
        try:
            for membro in membri:
                if operazione.ferma:
                    interrotta = "fermata a mano"
                    break
                try:
                    if operazione.azione == AZIONE_DAI:
                        await membro.add_roles(ruolo, reason=motivo)
                    else:
                        await membro.remove_roles(ruolo, reason=motivo)
                    operazione.fatti += 1
                    errori_di_fila = 0
                except discord.HTTPException as errore:
                    operazione.falliti += 1
                    errori_di_fila += 1
                    if errori_di_fila >= MAX_ERRORI_DI_FILA:
                        interrotta = f"troppi errori di fila (ultimo: {errore.text or errore})"[:300]
                        break
                await asyncio.sleep(PAUSA_MASSA_SECONDI)
        except Exception:  # noqa: BLE001 — l'avviso finale deve partire comunque
            logger.exception("Operazione di massa interrotta nel server %s", guild.id)
            interrotta = "errore inatteso"
        finally:
            self.operazioni.pop(guild.id, None)
            await self._avviso_finale(canale, ruolo, operazione, interrotta)

    @staticmethod
    async def _avviso_finale(canale, ruolo, operazione: OperazioneMassa, interrotta: str | None) -> None:
        verbo = "dato" if operazione.azione == AZIONE_DAI else "tolto"
        testo = (
            f"Operazione di massa su {ruolo.mention} finita: {verbo} a {operazione.fatti} membri, "
            f"{operazione.falliti} non riusciti, su {operazione.totale}."
        )
        if interrotta:
            testo = f"Operazione di massa su {ruolo.mention} interrotta ({interrotta}): " \
                    f"{verbo} a {operazione.fatti} membri, {operazione.falliti} non riusciti, su {operazione.totale}."
        if operazione.autore_id:
            testo += f" Avviata da <@{operazione.autore_id}>."
        if canale is None:
            return
        try:
            await canale.send(testo[:1900], allowed_mentions=NESSUNA_MENZIONE)
        except discord.HTTPException:
            logger.warning("Avviso finale dell'operazione di massa non inviato")

    @comando_di_gruppo("ruoli", nome="massa-ferma", descrizione="Ferma l'operazione di massa in corso.")
    async def massa_ferma(self, interaction: discord.Interaction) -> None:
        operazione = self.operazioni.get(interaction.guild.id)
        if operazione is None:
            await self._rifiuta(interaction, "Non c'è nessuna operazione di massa in corso.")
            return
        operazione.ferma = True
        await interaction.response.send_message(
            f"Fermo l'operazione: fatti {operazione.fatti} su {operazione.totale}. L'avviso finale arriva nel canale scelto.",
            ephemeral=True,
        )

    # ================================================================
    # Crea, modifica, diagnosi
    # ================================================================
    @comando_di_gruppo("ruoli", nome="crea", descrizione="Crea un ruolo nuovo.")
    @app_commands.describe(
        nome="Il nome del ruolo",
        colore="Colore, es. #FF8800",
        menzionabile="Tutti possono menzionarlo?",
        separato="Mostrato a parte nella lista dei membri?",
    )
    async def crea(
        self,
        interaction: discord.Interaction,
        nome: app_commands.Range[str, 1, 100],
        colore: app_commands.Range[str, 4, 7] | None = None,
        menzionabile: bool = False,
        separato: bool = False,
    ) -> None:
        guild = interaction.guild
        if len(guild.roles) >= MAX_RUOLI_SERVER:
            await self._rifiuta(interaction, f"Il server ha già {MAX_RUOLI_SERVER} ruoli, il massimo di Discord.")
            return
        try:
            tinta = colore_ruolo(colore)
        except ValueError as errore:
            await self._rifiuta(interaction, str(errore))
            return
        try:
            nuovo = await guild.create_role(
                name=nome,
                colour=tinta or discord.Colour.default(),
                mentionable=menzionabile,
                hoist=separato,
                reason=motivo_audit(interaction.user, "Ruolo creato da comando"),
            )
        except discord.HTTPException as errore:
            await self._rifiuta(interaction, f"Discord ha rifiutato: {errore.text or errore}"[:1900])
            return
        await interaction.response.send_message(f"Creato {nuovo.mention}.", ephemeral=True, allowed_mentions=NESSUNA_MENZIONE)

    @comando_di_gruppo("ruoli", nome="modifica", descrizione="Cambia nome, colore e opzioni di un ruolo.")
    @app_commands.describe(
        ruolo="Il ruolo da cambiare",
        nome="Il nome nuovo",
        colore="Colore nuovo, es. #FF8800",
        menzionabile="Tutti possono menzionarlo?",
        separato="Mostrato a parte nella lista dei membri?",
    )
    async def modifica(
        self,
        interaction: discord.Interaction,
        ruolo: discord.Role,
        nome: app_commands.Range[str, 1, 100] | None = None,
        colore: app_commands.Range[str, 4, 7] | None = None,
        menzionabile: bool | None = None,
        separato: bool | None = None,
    ) -> None:
        guild = interaction.guild
        problemi = diagnosi_ruolo(ruolo, bot_gestisce_ruoli=True, ruolo_bot_piu_alto=guild.me.top_role)
        if not problemi and interaction.user.id != guild.owner_id and ruolo >= interaction.user.top_role:
            problemi = ["È pari o sopra il tuo ruolo più alto."]
        if problemi:
            await self._rifiuta(interaction, "Non posso cambiarlo: " + " ".join(problemi))
            return
        try:
            tinta = colore_ruolo(colore)
        except ValueError as errore:
            await self._rifiuta(interaction, str(errore))
            return
        modifiche: dict = {}
        if nome is not None:
            modifiche["name"] = nome
        if tinta is not None:
            modifiche["colour"] = tinta
        if menzionabile is not None:
            modifiche["mentionable"] = menzionabile
        if separato is not None:
            modifiche["hoist"] = separato
        if not modifiche:
            await self._rifiuta(interaction, "Scegli almeno una cosa da cambiare.")
            return
        try:
            await ruolo.edit(**modifiche, reason=motivo_audit(interaction.user, "Ruolo modificato da comando"))
        except discord.HTTPException as errore:
            await self._rifiuta(interaction, f"Discord ha rifiutato: {errore.text or errore}"[:1900])
            return
        await interaction.response.send_message(f"{ruolo.mention} aggiornato.", ephemeral=True, allowed_mentions=NESSUNA_MENZIONE)

    @comando_di_gruppo("ruoli", nome="diagnosi", descrizione="Scopri perché il bot non riesce a dare un ruolo.")
    @app_commands.describe(ruolo="Il ruolo da controllare")
    async def diagnosi(self, interaction: discord.Interaction, ruolo: discord.Role) -> None:
        guild = interaction.guild
        problemi = diagnosi_ruolo(
            ruolo,
            bot_gestisce_ruoli=guild.me.guild_permissions.manage_roles,
            ruolo_bot_piu_alto=guild.me.top_role,
        )
        if problemi:
            testo = f"Il bot **non** può dare {ruolo.mention}:\n" + "\n".join(f"- {p}" for p in problemi)
        else:
            testo = f"Il bot può dare {ruolo.mention}."
        await interaction.response.send_message(testo[:1900], ephemeral=True, allowed_mentions=NESSUNA_MENZIONE)

    # ================================================================
    # Ruoli a scelta
    # ================================================================
    @comando_di_gruppo("ruoli", nome="scelta", descrizione="Ruoli che i membri si prendono da soli con /utility ruolo.")
    @app_commands.describe(azione="Cosa fare", ruolo="Il ruolo (per aggiungi e rimuovi)")
    @app_commands.choices(
        azione=[
            app_commands.Choice(name="aggiungi", value="aggiungi"),
            app_commands.Choice(name="rimuovi", value="rimuovi"),
            app_commands.Choice(name="svuota", value="svuota"),
            app_commands.Choice(name="elenco", value="elenco"),
        ]
    )
    async def scelta(self, interaction: discord.Interaction, azione: str, ruolo: discord.Role | None = None) -> None:
        guild = interaction.guild
        if azione in ("aggiungi", "rimuovi") and ruolo is None:
            await self._rifiuta(interaction, "Indica il ruolo.")
            return
        if azione == "aggiungi":
            problema = self._primo_problema(guild, [ruolo], interaction.user, self_service=True)
            if problema is not None:
                await self._rifiuta(interaction, problema)
                return
            if not await self_role_repo.add(guild.id, ruolo.id, interaction.user.id):
                await self._rifiuta(interaction, f"Ci sono già {MAX_RUOLI_SCELTA} ruoli a scelta: togline uno prima.")
                return
            testo = f"{ruolo.mention} ora si può prendere con /utility ruolo."
        elif azione == "rimuovi":
            tolto = await self_role_repo.remove(guild.id, ruolo.id)
            testo = f"{ruolo.mention} non è più a scelta." if tolto else f"{ruolo.mention} non era a scelta."
        elif azione == "svuota":
            quanti = await self_role_repo.clear(guild.id)
            testo = f"Tolti {quanti} ruoli a scelta."
        else:
            ids = await self_role_repo.list_ids(guild.id)
            testo = "Ruoli a scelta: " + (", ".join(f"<@&{i}>" for i in ids) or "nessuno.")
        await interaction.response.send_message(testo[:1900], ephemeral=True, allowed_mentions=NESSUNA_MENZIONE)

    async def _ruoli_a_scelta(self, guild: discord.Guild) -> list[discord.Role]:
        """I ruoli a scelta che esistono ancora e che il bot può dare.
        I permessi si ricontrollano qui: un ruolo diventato «forte» dopo l'aggiunta non si prende più."""
        ruoli = [guild.get_role(i) for i in await self_role_repo.list_ids(guild.id)]
        return [
            r for r in ruoli
            if r is not None and check_role_assignable(guild, r, guild.me, self_service=True) is None
        ]

    async def applica_scelta(self, membro: discord.Member, da_avere: set[int], da_lasciare: set[int]) -> str:
        """Dà i ruoli scelti che mancano e toglie quelli lasciati; solo tra i ruoli a scelta."""
        guild = membro.guild
        ammessi = {r.id: r for r in await self._ruoli_a_scelta(guild)}
        posseduti = {r.id for r in membro.roles}
        dai = [ammessi[i] for i in da_avere if i in ammessi and i not in posseduti]
        togli = [ammessi[i] for i in da_lasciare if i in ammessi and i in posseduti]
        try:
            if dai:
                await membro.add_roles(*dai, reason="Ruolo a scelta")
            if togli:
                await membro.remove_roles(*togli, reason="Ruolo a scelta")
        except discord.HTTPException:
            return "Discord ha rifiutato il cambio: avvisa lo staff (/ruoli diagnosi)."
        if not dai and not togli:
            return "Nessun cambio."
        parti = []
        if dai:
            parti.append("presi " + ", ".join(r.mention for r in dai))
        if togli:
            parti.append("lasciati " + ", ".join(r.mention for r in togli))
        return ("Fatto: " + "; ".join(parti) + ".")[:1900]

    async def _suggerisci_scelta(self, interaction: discord.Interaction, corrente: str) -> list[app_commands.Choice[str]]:
        if interaction.guild is None:
            return []
        cercato = corrente.lower()
        return [
            app_commands.Choice(name=r.name[:100], value=str(r.id))
            for r in await self._ruoli_a_scelta(interaction.guild)
            if cercato in r.name.lower()
        ][:25]

    @comando_di_gruppo("utility", nome="ruolo", descrizione="Prendi o lascia i ruoli a scelta del server.")
    @app_commands.describe(ruolo="Un ruolo da prendere o lasciare (vuoto = menu con tutti)")
    @app_commands.autocomplete(ruolo=_suggerisci_scelta)
    @app_commands.checks.cooldown(1, 5)
    async def ruolo_a_scelta(self, interaction: discord.Interaction, ruolo: app_commands.Range[str, 1, 20] | None = None) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("Questo comando funziona solo in un server.", ephemeral=True)
            return
        ruoli = await self._ruoli_a_scelta(guild)
        if not ruoli:
            await interaction.response.send_message("Questo server non ha ruoli a scelta.", ephemeral=True)
            return
        if ruolo is None:
            await interaction.response.send_message(
                "Segna i ruoli che vuoi avere; togli il segno per lasciarli.",
                view=SceltaRuoliView(self, interaction.user, ruoli),
                ephemeral=True,
            )
            return
        scelto = next((r for r in ruoli if str(r.id) == ruolo.strip()), None)
        if scelto is None:
            await interaction.response.send_message("Questo ruolo non è a scelta: sceglilo dall'elenco.", ephemeral=True)
            return
        if any(r.id == scelto.id for r in interaction.user.roles):
            testo = await self.applica_scelta(interaction.user, set(), {scelto.id})
        else:
            testo = await self.applica_scelta(interaction.user, {scelto.id}, set())
        await interaction.response.send_message(testo, ephemeral=True, allowed_mentions=NESSUNA_MENZIONE)


async def setup(bot: commands.Bot) -> None:
    cog = RuoliStrumentiCog(bot)
    await bot.add_cog(cog)
    scheduler.register_handler(RUOLI_TEMPORANEI_ACTION_TYPE, cog.handle_ruoli_temporanei)
