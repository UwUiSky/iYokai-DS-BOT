"""
cogs/logging/logs_query.py
=============================
Interfaccia comandi sul log eventi unificato (BACKLOG.md §3):
/log cerca utente, /log cerca canale, /log esporta. Nessuna logica propria
oltre alla formattazione — legge tramite core/repositories/
event_log_repo.py, scritto da cogs/logging/basic_logs.py.
/log archivio-canale scarica gli ultimi messaggi di un canale in un file,
con quelli cancellati nell'ultima ora (LOG-027, LOG-030).
Funzioni coperte: SPEC §8.17, §8.18 (LOG-027, LOG-030)

Nessun gate is_module_active_for_guild qui: se il modulo è
disattivato, semplicemente non c'è nulla da mostrare (la tabella
resta vuota per quel server) — non serve bloccare il comando stesso,
che a differenza dei listener non ha nessun costo continuo.

Limiti: ogni voce è tagliata e l'elenco si ferma a 4000 caratteri
(descrizione di un embed: 4096); l'export è diviso in più file, ognuno
sotto i 10 MiB.
"""

from __future__ import annotations

import io
import json
import logging

import discord
from discord import app_commands
from discord.ext import commands

from cogs.logging import message_logs
from core import channel_router as router
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.message_log_logic import ARCHIVIO_BYTE_MAX, ARCHIVIO_MESSAGGI_MAX, file_archivio
from core.repositories.event_log_repo import EventLogEntry, event_log_repo


logger = logging.getLogger("iyokai.logging.query")

# La descrizione di un embed tiene 4096 caratteri (LIM-15). Con i
# dettagli tagliati a 50 caratteri entrano tutte le 25 voci; se una
# volta non bastasse, l'elenco si ferma a 4000 e dice quante ne mancano.
MAX_DETAILS_LENGTH = 50
MAX_LIST_LENGTH = 4000

# Un file allegato deve restare sotto i 10 MiB (LIM-55). Ci fermiamo a
# 8 per lasciare margine al resto della richiesta.
MAX_EXPORT_FILE_BYTES = 8 * 1024 * 1024
# Server con un /log archivio-canale in corso (uno alla volta per server).
_archivi_in_corso: set[int] = set()


def _format_entry(entry: EventLogEntry) -> str:
    quando = discord.utils.format_dt(entry.created_at, style="R")
    pezzi = [f"`#{entry.id}` **{entry.event_type}** — {quando}"]
    if entry.actor_id:
        pezzi.append(f"da <@{entry.actor_id}>")
    if entry.case_number:
        pezzi.append(f"(caso #{entry.case_number})")
    if entry.details:
        # L'accento grave chiuderebbe il blocco di codice a metà.
        dettagli = json.dumps(entry.details, ensure_ascii=False).replace("`", "'")
        if len(dettagli) > MAX_DETAILS_LENGTH:
            dettagli = dettagli[: MAX_DETAILS_LENGTH - 1] + "…"
        pezzi.append(f"`{dettagli}`")
    return " ".join(pezzi)


def _format_entries(entries: list[EventLogEntry]) -> str:
    """Una voce per riga, finché stanno nella descrizione di un embed."""
    mostrate: list[str] = []
    lunghezza = 0
    for entry in entries:
        riga = _format_entry(entry)
        lunghezza += len(riga) + 1  # 1 = l'a capo
        if lunghezza > MAX_LIST_LENGTH:
            break
        mostrate.append(riga)

    testo = "\n".join(mostrate)
    escluse = len(entries) - len(mostrate)
    if escluse:
        testo += f"\n…e altre {escluse} voci: usa /log esporta per vederle tutte."
    return testo


def split_export(events: list[dict], max_bytes: int) -> list[bytes]:
    """
    Divide gli eventi in più file JSON, ognuno una lista valida e
    ognuno entro `max_bytes`. Restituisce sempre almeno un file (una
    lista vuota se non ci sono eventi). Un singolo evento più grande
    del limite finisce da solo nel suo file.
    """
    parti: list[bytes] = []
    voci: list[bytes] = []
    peso = 2  # le due parentesi quadre

    def chiudi() -> None:
        parti.append(b"[\n" + b",\n".join(voci) + b"\n]")

    for event in events:
        voce = json.dumps(event, ensure_ascii=False, indent=2).encode("utf-8")
        peso_voce = len(voce) + 2  # virgola e a capo
        if voci and peso + peso_voce + 2 > max_bytes:
            chiudi()
            voci, peso = [], 2
        voci.append(voce)
        peso += peso_voce

    if voci or not parti:
        chiudi()
    return parti


class LogsQueryCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @comando_di_gruppo(
        "log",
        nome="utente",
        descrizione="Mostra lo storico eventi di un utente.",
        sottogruppo=("cerca", "Cerca nello storico eventi del server."),
    )
    @app_commands.describe(
        member="L'utente da consultare", limit="Quante voci mostrare (default 15, massimo 25)"
    )
    async def logs_user(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        limit: app_commands.Range[int, 1, 25] = 15,
    ) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return

        eventi = await event_log_repo.get_events_by_user(guild.id, member.id, limit=limit)
        if not eventi:
            await interaction.response.send_message(
                f"Nessun evento registrato per {member.mention}.", ephemeral=True
            )
            return

        embed = discord.Embed(
            title=f"📜 Storico eventi — {member}",
            description=_format_entries(eventi),
            color=discord.Color.blurple(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @comando_di_gruppo(
        "log",
        nome="canale",
        descrizione="Mostra lo storico eventi di un canale.",
        sottogruppo=("cerca", "Cerca nello storico eventi del server."),
    )
    @app_commands.describe(
        channel="Il canale da consultare", limit="Quante voci mostrare (default 15, massimo 25)"
    )
    async def logs_channel(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        limit: app_commands.Range[int, 1, 25] = 15,
    ) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return

        eventi = await event_log_repo.get_events_by_channel(guild.id, channel.id, limit=limit)
        if not eventi:
            await interaction.response.send_message(
                f"Nessun evento registrato per {channel.mention}.", ephemeral=True
            )
            return

        embed = discord.Embed(
            title=f"📜 Storico eventi — #{channel.name}",
            description=_format_entries(eventi),
            color=discord.Color.blurple(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @comando_di_gruppo(
        "log",
        nome="esporta",
        descrizione="Esporta lo storico eventi completo del server come file JSON.",
    )
    async def logs_export(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        eventi = await event_log_repo.export_events(guild.id)
        payload = [
            {
                "id": e.id,
                "event_type": e.event_type,
                "actor_id": e.actor_id,
                "target_user_id": e.target_user_id,
                "channel_id": e.channel_id,
                "role_id": e.role_id,
                "case_number": e.case_number,
                "details": e.details,
                "created_at": e.created_at.isoformat(),
            }
            for e in eventi
        ]
        parti = split_export(payload, MAX_EXPORT_FILE_BYTES)
        totale = len(parti)
        try:
            for numero, parte in enumerate(parti, start=1):
                if totale == 1:
                    nome = f"event_log_{guild.id}.json"
                    testo = f"Export completo: {len(eventi)} eventi."
                else:
                    nome = f"event_log_{guild.id}_parte_{numero}_di_{totale}.json"
                    testo = f"Export completo: {len(eventi)} eventi. File {numero} di {totale}."
                await interaction.followup.send(
                    testo,
                    file=discord.File(io.BytesIO(parte), filename=nome),
                    ephemeral=True,
                )
        except discord.HTTPException as errore:
            logger.warning("Export dei log non inviato (server %s): %s", guild.id, errore)
            await interaction.followup.send(
                "Non sono riuscito a inviare il file dell'export. Riprova tra poco.",
                ephemeral=True,
            )


    @comando_di_gruppo(
        "log",
        nome="archivio-canale",
        descrizione="Scarica in un file gli ultimi messaggi di un canale, anche quelli appena cancellati.",
    )
    @app_commands.describe(
        canale="Il canale da archiviare",
        messaggi=f"Quanti messaggi, dai più recenti (default 200, massimo {ARCHIVIO_MESSAGGI_MAX})",
    )
    async def archivio_canale(
        self,
        interaction: discord.Interaction,
        canale: discord.TextChannel,
        messaggi: app_commands.Range[int, 1, ARCHIVIO_MESSAGGI_MAX] = 200,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("Questo comando funziona solo in un server.", ephemeral=True)
            return
        tuoi = canale.permissions_for(interaction.user)
        if not (tuoi.view_channel and tuoi.read_message_history):
            await interaction.response.send_message("Non puoi leggere la cronologia di quel canale.", ephemeral=True)
            return
        miei = canale.permissions_for(interaction.guild.me)
        if router.canale_nascosto(canale) or not (miei.view_channel and miei.read_message_history):
            await interaction.response.send_message(
                "Non posso leggere la cronologia di quel canale (mi serve «Leggere la cronologia»).", ephemeral=True
            )
            return
        # Un archivio alla volta per server: 20.000 messaggi pesano su memoria e rate limit.
        if interaction.guild.id in _archivi_in_corso:
            await interaction.response.send_message(
                "Sto già preparando un archivio per questo server. Riprova quando è pronto.", ephemeral=True
            )
            return
        _archivi_in_corso.add(interaction.guild.id)
        try:
            await self._archivio(interaction, canale, messaggi)
        finally:
            _archivi_in_corso.discard(interaction.guild.id)

    async def _archivio(self, interaction: discord.Interaction, canale: discord.TextChannel, messaggi: int) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        letti = []
        peso = 0
        troncato = False
        try:
            async for m in canale.history(limit=messaggi):
                voce = message_logs.archiviato(m)
                peso += len(voce.testo.encode("utf-8")) + len(voce.author_nome.encode("utf-8")) + 64
                if peso > ARCHIVIO_BYTE_MAX:
                    troncato = True
                    break
                letti.append(voce)
        except discord.HTTPException as errore:
            logger.warning("Archivio del canale %s interrotto: %s", canale.id, errore)
        cancellati = message_logs.cancellati_recenti.di(canale.id)
        parti = file_archivio(canale.name, letti, cancellati, MAX_EXPORT_FILE_BYTES)
        if troncato:
            limite = ARCHIVIO_BYTE_MAX // (1024 * 1024)
            await interaction.followup.send(
                f"Mi sono fermato a {len(letti)} messaggi: oltre {limite} MiB di testo l'archivio non si fa.",
                ephemeral=True,
            )
        try:
            for numero, parte in enumerate(parti, start=1):
                nome = f"archivio_{canale.name}.txt" if len(parti) == 1 else f"archivio_{canale.name}_{numero}.txt"
                await interaction.followup.send(
                    f"Archivio di {canale.mention}: {len(letti)} messaggi, {len(cancellati)} cancellati di recente."
                    + (f" File {numero} di {len(parti)}." if len(parti) > 1 else ""),
                    file=discord.File(io.BytesIO(parte), filename=nome),
                    ephemeral=True,
                )
        except discord.HTTPException as errore:
            logger.warning("Archivio del canale %s non inviato: %s", canale.id, errore)
            await interaction.followup.send("Non sono riuscito a mandare il file. Riprova tra poco.", ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(LogsQueryCog(bot))
