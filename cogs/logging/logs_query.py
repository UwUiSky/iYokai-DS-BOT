"""
cogs/logging/logs_query.py
=============================
Interfaccia comandi sul log eventi unificato (BACKLOG.md §3):
/logs user, /logs channel, /logs export. Nessuna logica propria
oltre alla formattazione — legge tramite core/repositories/
event_log_repo.py, scritto da cogs/logging/basic_logs.py.

Nessun gate is_module_active_for_guild qui: se il modulo è
disattivato, semplicemente non c'è nulla da mostrare (la tabella
resta vuota per quel server) — non serve bloccare il comando stesso,
che a differenza dei listener non ha nessun costo continuo.

Limiti: ogni voce è tagliata e l'elenco si ferma a 4000 caratteri
(descrizione di un embed: 4096); l'export è diviso in più file, ognuno
sotto i 10 MiB.
"""

# DA FARE (issue #61, fase F1): correzioni aperte per questo file in
#   revisione/02-piano/MODIFICHE_ESISTENTE.md §5 (Log).

from __future__ import annotations

import io
import json
import logging

import discord
from discord import app_commands
from discord.ext import commands

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
        testo += f"\n…e altre {escluse} voci: usa /logs export per vederle tutte."
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


class LogsQueryCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    logs_group = app_commands.Group(
        name="logs", description="Consulta lo storico eventi del server."
    )

    @logs_group.command(name="user", description="[Admin] Mostra lo storico eventi di un utente.")
    @app_commands.describe(
        member="L'utente da consultare", limit="Quante voci mostrare (default 15, massimo 25)"
    )
    @app_commands.checks.has_permissions(manage_guild=True)
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

    @logs_group.command(
        name="channel", description="[Admin] Mostra lo storico eventi di un canale."
    )
    @app_commands.describe(
        channel="Il canale da consultare", limit="Quante voci mostrare (default 15, massimo 25)"
    )
    @app_commands.checks.has_permissions(manage_guild=True)
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

    @logs_group.command(
        name="export",
        description="[Admin] Esporta lo storico eventi completo del server come file JSON.",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
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


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(LogsQueryCog(bot))
