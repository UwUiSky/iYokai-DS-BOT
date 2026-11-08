"""
cogs/tickets/inattivita.py
==========================
Giro periodico sui ticket aperti: categoria «in attesa dell'utente» (TKT-029), regole di
inattività per pannello (TKT-064) e riserva di canali già pronti (TKT-035).
Le regole stanno in core/ticket_autoclose_worker.py; lo stato nel database (migrazione 0534):
un riavvio del bot non perde nulla.
Funzioni coperte: SPEC §13.20 (TKT-029, TKT-035, TKT-064)
Dipende da: cogs/tickets/tickets.py (chiusura da sistema)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import discord
from discord.ext import commands, tasks

from cogs.tickets.tickets import _opzioni_pannello
from core import ticket_autoclose_worker as regole
from core.i18n import testo_guild
from core.repositories.ticket_automazioni_repo import ticket_automazioni_repo as repo
from core.repositories.ticket_repo import ticket_repo
from core.ticket_autoclose_worker import Regola

logger = logging.getLogger("iyokai.tickets.inattivita")

GIRO_MINUTI = 2
MAX_TICKET_PER_GIRO = 300
NIENTE = discord.AllowedMentions.none()


class TicketInattivitaCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._regole: dict[int, list[Regola]] = {}
        self._dopo_id = 0  # il giro riprende dal ticket dopo l'ultimo controllato

    async def cog_load(self) -> None:
        self._giro.start()

    async def cog_unload(self) -> None:
        self._giro.cancel()

    @tasks.loop(minutes=GIRO_MINUTI)
    async def _giro(self) -> None:
        try:
            await self.controlla_ticket(datetime.now(timezone.utc))
        except Exception:  # noqa: BLE001 - il giro non deve mai fermarsi
            logger.exception("Giro sui ticket fermi non riuscito")
        try:
            await self.rifornisci_riserva()
        except Exception:  # noqa: BLE001
            logger.exception("Rifornimento della riserva di canali non riuscito")

    @_giro.before_loop
    async def _prima_del_giro(self) -> None:
        await self.bot.wait_until_ready()

    # ------------------------------------------------------------ ticket aperti
    async def controlla_ticket(self, adesso: datetime) -> None:
        self._regole = {}
        righe = await repo.da_controllare(self._dopo_id, MAX_TICKET_PER_GIRO)
        # Meno righe del tetto = arrivati in fondo: il giro dopo riparte dal primo.
        self._dopo_id = righe[-1]["id"] if len(righe) == MAX_TICKET_PER_GIRO else 0
        for riga in righe:
            try:
                await self._un_ticket(riga, adesso)
            except Exception:  # noqa: BLE001 - un ticket che dà errore non ferma gli altri
                logger.exception("Controllo del ticket %s non riuscito", riga["id"])

    async def _regole_del_pannello(self, panel_id: int) -> list[Regola]:
        if panel_id not in self._regole:
            self._regole[panel_id] = await repo.regole(panel_id)
        return self._regole[panel_id]

    async def _un_ticket(self, riga: dict, adesso: datetime) -> None:
        guild = self.bot.get_guild(riga["guild_id"])
        channel = guild.get_channel_or_thread(riga["channel_id"]) if guild is not None else None
        if channel is None:
            return
        if isinstance(channel, discord.TextChannel):
            await self._attesa(guild, channel, riga, adesso)
        regole_pannello = await self._regole_del_pannello(riga["panel_id"])
        eseguite = await repo.eseguite(riga["id"]) if regole_pannello else {}
        for regola in regole_pannello:
            scattata = regole.regola_scattata(
                regola,
                creato=riga["created_at"],
                ultimo_utente=riga["ultimo_utente_at"],
                ultimo_staff=riga["ultimo_staff_at"],
                ultima_attivita=riga["last_activity_at"],
                ultima_esecuzione=eseguite.get(regola.id),
                adesso=adesso,
            )
            if scattata and await self._esegui(guild, channel, riga, regola, adesso):
                return  # chiuso o eliminato: le altre regole non servono

    # ------------------------------------------------------------ TKT-029
    async def _attesa(self, guild, channel: discord.TextChannel, riga: dict, adesso: datetime) -> None:
        in_attesa = riga["in_attesa_da"] is not None
        if regole.da_riportare_indietro(
            in_attesa=in_attesa, in_attesa_da=riga["in_attesa_da"], ultimo_utente=riga["ultimo_utente_at"],
            spostato_at=riga["spostato_at"], adesso=adesso,
        ):
            destinazione = guild.get_channel(riga["categoria_prima_attesa"] or 0)
            if isinstance(destinazione, discord.CategoryChannel) and not regole.categoria_con_posto(len(destinazione.channels)):
                logger.info("Categoria piena: il ticket %s resta in attesa.", channel.id)
                return
            if isinstance(destinazione, discord.CategoryChannel):
                await channel.edit(category=destinazione, reason="L'utente ha risposto: il ticket torna tra gli aperti")
            await repo.segna_ritorno(riga["id"], adesso)
            return
        if not regole.da_mettere_in_attesa(
            attesa_minuti=riga["attesa_minuti"], in_attesa=in_attesa, ultimo_utente=riga["ultimo_utente_at"],
            ultimo_staff=riga["ultimo_staff_at"], spostato_at=riga["spostato_at"], adesso=adesso,
        ):
            return
        destinazione = guild.get_channel(riga["attesa_categoria_id"] or 0)
        if not isinstance(destinazione, discord.CategoryChannel):
            return
        if not regole.categoria_con_posto(len(destinazione.channels)):
            logger.warning("Categoria «in attesa» piena (50 canali): il ticket %s non si sposta.", channel.id)
            return
        prima = channel.category_id
        await channel.edit(category=destinazione, reason="In attesa dell'utente")
        await repo.segna_attesa(riga["id"], prima, adesso)

    # ------------------------------------------------------------ TKT-064
    async def _esegui(self, guild, channel, riga: dict, regola: Regola, adesso: datetime) -> bool:
        """Esegue la regola. Vero se il ticket è stato chiuso (le altre regole si fermano)."""
        if regola.azione == "messaggio":
            testo = (regola.testo or "").replace("{utente}", f"<@{riga['user_id']}>")[:2000]
            await channel.send(testo, allowed_mentions=discord.AllowedMentions(users=[discord.Object(riga["user_id"])]))
            await repo.segna_eseguita(riga["id"], regola.id, adesso)
            return False
        cog = self.bot.get_cog("TicketsCog")
        ticket = await ticket_repo.get_ticket_by_channel(channel.id)
        if cog is None or ticket is None or ticket.status != "open":
            return False
        await repo.segna_eseguita(riga["id"], regola.id, adesso)
        # Con la chiusura in due passi il canale resta, a meno che la regola non lo elimini.
        resta = (await _opzioni_pannello(ticket.panel_id)).chiusura_due_passi and regola.azione != "elimina"
        avviso = " ".join([
            await testo_guild(guild, "tickets_regola_chiusura", minuti=regola.minuti),
            await testo_guild(guild, "tickets_canale_resta_chiuso" if resta else "tickets_canale_eliminato_presto"),
        ])
        chiuso = await cog._chiudi_da_sistema(
            guild, channel, ticket, motivo="Ticket chiuso da una regola di inattività", avviso=avviso,
            chiedi_voto=True, ragione="Chiuso per inattività (regola del pannello)", avviso_pronto=True,
        )
        if chiuso and regola.azione == "elimina":
            await cog._pianifica_eliminazione_canale(
                guild.id, guild.me.id, channel.id, "Eliminato da una regola di inattività", 30
            )
        return chiuso

    # ------------------------------------------------------------ TKT-035
    async def rifornisci_riserva(self) -> None:
        """Un canale vuoto per giro e per pannello, al massimo: niente creazioni di massa."""
        for riga in await repo.pannelli_con_riserva():
            guild = self.bot.get_guild(riga["guild_id"])
            categoria = guild.get_channel(riga["category_id"]) if guild is not None else None
            if not isinstance(categoria, discord.CategoryChannel):
                continue
            if riga["riserva_canali"] == 0:
                await self._svuota_riserva(guild, riga["panel_id"])
                continue
            if not regole.canali_da_creare(riga["riserva_canali"], riga["presenti"]):
                continue
            if not regole.categoria_con_posto(len(categoria.channels)):
                logger.warning("Categoria dei ticket piena: la riserva del pannello %s non cresce.", riga["panel_id"])
                continue
            try:
                canale = await categoria.create_text_channel(
                    name="ticket-pronto",
                    overwrites={
                        guild.default_role: discord.PermissionOverwrite(view_channel=False),
                        guild.me: discord.PermissionOverwrite(view_channel=True, manage_channels=True, send_messages=True),
                    },
                    reason="Riserva di canali per i ticket",
                )
            except discord.HTTPException:
                logger.warning("Canale di riserva non creato per il pannello %s.", riga["panel_id"])
                continue
            await repo.aggiungi_riserva(canale.id, guild.id, riga["panel_id"])

    async def _svuota_riserva(self, guild, panel_id: int) -> None:
        while (canale_id := await repo.prendi_riserva(panel_id)) is not None:
            canale = guild.get_channel(canale_id)
            if canale is not None:
                try:
                    await canale.delete(reason="Riserva di canali spenta")
                except discord.HTTPException:
                    logger.warning("Canale di riserva %s non eliminato.", canale_id)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(TicketInattivitaCog(bot))
