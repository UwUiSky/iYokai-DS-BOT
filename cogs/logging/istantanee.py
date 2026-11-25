"""
cogs/logging/istantanee.py
==========================
/admin-log istantanea: un canale in una pagina del pannello web, con scadenza e scelta di chi la vede (LOG-028).
Crea (gli ultimi messaggi, anche quelli appena cancellati, senza i file: solo i nomi), elenca e toglie.
Il link ha un segreto lungo che si mostra una sola volta, solo a chi ha dato il comando; nel database resta
l'impronta. Si apre solo con l'accesso con Discord (`core/web_panel_istantanee.py`). Mai visibile a tutti.
Funzioni coperte: SPEC §8.21 (LOG-028), D95
Dipende da: core/log_istantanee_logic.py, core/repositories/log_istantanee_repo.py, cogs/logging/message_logs.py
"""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from cogs.logging import message_logs
from core import channel_router as router
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.config import config
from core.i18n import testo_per
from core.log_istantanee_logic import (
    ACCESSI,
    ATTIVE_MAX_PER_SERVER,
    GIORNI_BASE,
    GIORNI_MAX,
    MESSAGGI_BASE,
    MESSAGGI_MAX,
    impronta,
    nuovo_segreto,
    righe_istantanea,
)
from core.message_log_logic import da_ignorare
from core.repositories.event_log_repo import event_log_repo
from core.repositories.log_eventi_repo import log_eventi_repo
from core.repositories.log_ignora_repo import log_ignora_repo
from core.repositories.log_istantanee_repo import log_istantanee_repo
from core.giro_periodico import giro_periodico

logger = logging.getLogger("iyokai.logging.istantanee")

AZIONI = ("crea", "elenco", "revoca")


def indirizzo(base: str | None, segreto: str) -> str | None:
    """Il link da dare a chi ha creato l'istantanea; None se il pannello web non ha un indirizzo pubblico."""
    base = (base or "").rstrip("/")
    return f"{base}/istantanea/{segreto}" if base else None


class LogIstantaneeCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._in_corso: set[int] = set()  # un'istantanea alla volta per server
        self._pulizia = giro_periodico(hours=1)(self._giro_pulizia)

    async def cog_load(self) -> None:
        await super().cog_load()
        self._pulizia.start()

    async def cog_unload(self) -> None:
        self._pulizia.cancel()
        await super().cog_unload()

    async def _giro_pulizia(self) -> None:
        try:
            tolte = await log_istantanee_repo.pulisci_scadute()
            if tolte:
                logger.info("Istantanee scadute tolte: %d", tolte)
        except Exception:  # noqa: BLE001
            logger.warning("Pulizia delle istantanee non riuscita", exc_info=True)

    @comando_di_gruppo(
        "admin-log", nome="istantanea",
        descrizione="Un canale in una pagina web privata che scade. Crea, elenca o togli.",
    )
    @app_commands.describe(
        azione="Creare una istantanea, vedere quelle attive o toglierne una",
        canale="Il canale (per creare)",
        messaggi=f"Quanti messaggi, dai più recenti (default {MESSAGGI_BASE}, massimo {MESSAGGI_MAX})",
        giorni=f"Per quanti giorni resta aperta (default {GIORNI_BASE}, massimo {GIORNI_MAX})",
        accesso="Chi può vederla (default: solo chi gestisce il server)",
        ruolo="Il ruolo che la può vedere (serve con «ruolo»)",
        codice="Il numero dell'istantanea (per toglierla)",
    )
    @app_commands.choices(
        azione=[
            app_commands.Choice(name="Crea", value="crea"),
            app_commands.Choice(name="Elenco", value="elenco"),
            app_commands.Choice(name="Togli", value="revoca"),
        ],
        accesso=[
            app_commands.Choice(name="Solo chi gestisce il server", value="gestori"),
            app_commands.Choice(name="Chi gestisce il server e chi ha un ruolo", value="ruolo"),
            app_commands.Choice(name="I membri del server con il link", value="membri"),
        ],
    )
    async def istantanea(
        self,
        interaction: discord.Interaction,
        azione: str,
        canale: discord.TextChannel | None = None,
        messaggi: app_commands.Range[int, 1, MESSAGGI_MAX] = MESSAGGI_BASE,
        giorni: app_commands.Range[int, 1, GIORNI_MAX] = GIORNI_BASE,
        accesso: str = "gestori",
        ruolo: discord.Role | None = None,
        codice: app_commands.Range[int, 1, 10**15] | None = None,
    ) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(await testo_per(interaction, "ruolistrumen_questo_comando_funziona_solo_in"), ephemeral=True)
            return
        if azione == "elenco":
            await self._elenco(interaction)
        elif azione == "revoca":
            await self._revoca(interaction, codice)
        elif azione == "crea" and accesso in ACCESSI:
            await self._crea(interaction, canale, messaggi, giorni, accesso, ruolo)
        else:
            await interaction.response.send_message(await testo_per(interaction, "logist_scelta_non_valida"), ephemeral=True)

    async def _elenco(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        attive = await log_istantanee_repo.elenco(guild.id)
        if not attive:
            await interaction.response.send_message(await testo_per(interaction, "logist_nessuna"), ephemeral=True)
            return
        righe = []
        for i in attive:
            chi = await testo_per(interaction, f"logist_accesso_{i.accesso}")
            righe.append(
                f"#{i.id} · <#{i.channel_id}> · {chi} · {discord.utils.format_dt(i.scade_il, style='R')} · <@{i.creata_da}>"
            )
        await interaction.response.send_message("\n".join(righe)[:1900], ephemeral=True)

    async def _revoca(self, interaction: discord.Interaction, codice: int | None) -> None:
        if codice is None:
            await interaction.response.send_message(await testo_per(interaction, "logist_serve_codice"), ephemeral=True)
            return
        tolta = await log_istantanee_repo.revoca(interaction.guild.id, codice)
        await interaction.response.send_message(
            await testo_per(interaction, "logist_tolta" if tolta else "logist_non_trovata"), ephemeral=True
        )

    async def _crea(
        self, interaction: discord.Interaction, canale: discord.TextChannel | None, messaggi: int, giorni: int,
        accesso: str, ruolo: discord.Role | None,
    ) -> None:
        guild = interaction.guild
        if canale is None or canale.guild.id != guild.id:
            await interaction.response.send_message(await testo_per(interaction, "logist_serve_canale"), ephemeral=True)
            return
        if accesso == "ruolo" and (ruolo is None or ruolo.guild.id != guild.id or ruolo.is_default()):
            await interaction.response.send_message(await testo_per(interaction, "logist_serve_ruolo"), ephemeral=True)
            return
        if not indirizzo(config.WEB_PANEL_PUBLIC_URL, "x"):
            await interaction.response.send_message(await testo_per(interaction, "logist_pannello_spento"), ephemeral=True)
            return
        tuoi = canale.permissions_for(interaction.user)
        if not (tuoi.view_channel and tuoi.read_message_history):
            await interaction.response.send_message(await testo_per(interaction, "logsquery_non_puoi_leggere_la_cronologia"), ephemeral=True)
            return
        miei = canale.permissions_for(guild.me)
        if router.canale_nascosto(canale) or not (miei.view_channel and miei.read_message_history):
            await interaction.response.send_message(await testo_per(interaction, "logsquery_non_posso_leggere_la_cronologia"), ephemeral=True)
            return
        ignorati = await log_ignora_repo.carica(guild.id)
        if canale.id in ignorati.canali or (canale.category_id is not None and canale.category_id in ignorati.canali):
            await interaction.response.send_message(await testo_per(interaction, "logist_canale_ignorato"), ephemeral=True)
            return
        if guild.id in self._in_corso:
            await interaction.response.send_message(await testo_per(interaction, "logist_in_corso"), ephemeral=True)
            return
        self._in_corso.add(guild.id)
        try:
            await interaction.response.defer(ephemeral=True, thinking=True)
            await self._crea_pronta(interaction, canale, messaggi, giorni, accesso, ruolo, ignorati)
        finally:
            self._in_corso.discard(guild.id)

    async def _crea_pronta(self, interaction, canale, messaggi, giorni, accesso, ruolo, ignorati) -> None:
        guild = interaction.guild
        letti = []
        try:
            async for m in canale.history(limit=messaggi):
                if da_ignorare(
                    ignorati, channel_id=canale.id, author_id=m.author.id, testo=m.content,
                    category_id=canale.category_id, ruoli_autore=[r.id for r in getattr(m.author, "roles", [])],
                ):
                    continue
                letti.append(message_logs.archiviato(m))
        except discord.HTTPException as errore:
            logger.warning("Istantanea del canale %s interrotta: %s", canale.id, errore)
            await interaction.followup.send(await testo_per(interaction, "logist_lettura_fallita"), ephemeral=True)
            return
        cancellati = (
            message_logs.cancellati_recenti.di(canale.id)
            if await log_eventi_repo.evento_acceso(guild.id, "message_delete")
            else []
        )
        righe = righe_istantanea(letti, cancellati)
        segreto = nuovo_segreto()
        nuova = await log_istantanee_repo.crea(
            guild.id, canale.id, canale.name[:100], interaction.user.id, giorni, accesso,
            ruolo.id if accesso == "ruolo" and ruolo is not None else None, impronta(segreto), righe,
            ATTIVE_MAX_PER_SERVER,
        )
        if nuova is None:
            await interaction.followup.send(
                await testo_per(interaction, "logist_tetto", massimo=ATTIVE_MAX_PER_SERVER), ephemeral=True
            )
            return
        await event_log_repo.log_event(  # nessun segreto, nessun testo
            guild.id, "snapshot_create", actor_id=interaction.user.id, channel_id=canale.id,
            details={"id": nuova, "accesso": accesso, "giorni": giorni, "righe": len(righe)},
        )
        chi = await testo_per(interaction, f"logist_accesso_{accesso}")
        await interaction.followup.send(
            await testo_per(
                interaction, "logist_creata", link=indirizzo(config.WEB_PANEL_PUBLIC_URL, segreto), id=nuova,
                quanti=len(righe), giorni=giorni, accesso=chi,
            ),
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(LogIstantaneeCog(bot))
