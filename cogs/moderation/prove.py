"""
cogs/moderation/prove.py
========================
`/mod-casi caso prova`: allega una prova (immagine, PDF o TXT) a un caso, oppure, senza file, la mostra solo a chi
comanda. Le prove delle note si allegano con `/mod-casi nota aggiungi file:`. Regole e conservazione: core/moderation_prove.py.
Funzioni coperte: SPEC §5.2 (MOD-038)
"""

from __future__ import annotations

import io

import discord
from discord import app_commands
from discord.ext import commands

from cogs.moderation._shared import MODULE_CASE_SYSTEM, ensure_module_enabled, truncate_text
from core import moderation_prove as prove
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.i18n import testo_per
from core.repositories.moderation_repo import moderation_repo

INT4_MAX = 2_147_483_647
MAX_BYTE_RISPOSTA = 8 * 1024 * 1024  # sotto il limite dei file di Discord
SOTTOGRUPPO = ("caso", "Storico e dettagli dei casi di moderazione.")


async def allega_a_nota(interaction: discord.Interaction, utente_id: int, nota_id: int, allegato: discord.Attachment) -> str:
    """Conserva la prova di una nota appena creata. Restituisce il testo da aggiungere alla risposta."""
    esito = await prove.aggiungi_prova(
        interaction.guild.id, utente_id, interaction.user.id, nome_file=allegato.filename, dimensione=allegato.size,
        leggi=allegato.read, content_type=allegato.content_type, nota_id=nota_id,
    )
    chiave = esito.errore or "prove_aggiunta"
    return await testo_per(interaction, f"casesystem_{chiave}")


class ProveCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @comando_di_gruppo(
        "mod-casi", nome="prova", sottogruppo=SOTTOGRUPPO,
        descrizione="Allega una prova (immagine, PDF o TXT) a un caso; senza file mostra quelle già allegate.",
    )
    @app_commands.describe(numero="Il numero del caso", file="La prova: immagine, PDF o TXT fino a 10 MiB (al massimo 5 per caso)")
    async def prova(
        self, interaction: discord.Interaction, numero: app_commands.Range[int, 1, INT4_MAX], file: discord.Attachment | None = None
    ) -> None:
        if not await ensure_module_enabled(interaction, MODULE_CASE_SYSTEM):
            return
        caso = await moderation_repo.get_case(interaction.guild.id, numero)
        if caso is None:
            await interaction.response.send_message(
                await testo_per(interaction, "casesystem_nessun_caso_trovato_su_questo", case_number=numero), ephemeral=True
            )
            return
        if file is None:
            await self._mostra(interaction, numero)
            return
        await interaction.response.defer(ephemeral=True)
        esito = await prove.aggiungi_prova(
            interaction.guild.id, caso.user_id, interaction.user.id, nome_file=file.filename, dimensione=file.size,
            leggi=file.read, content_type=file.content_type, case_number=numero,
        )
        chiave = esito.errore or "prove_aggiunta"
        await interaction.followup.send(await testo_per(interaction, f"casesystem_{chiave}", numero=numero), ephemeral=True)

    async def _mostra(self, interaction: discord.Interaction, numero: int) -> None:
        guild_id = interaction.guild.id
        elenco = await moderation_repo.list_prove(guild_id, case_number=numero)
        if not elenco:
            await interaction.response.send_message(await testo_per(interaction, "casesystem_prove_nessuna", numero=numero), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        righe = [f"#{r['id']} {truncate_text(r['nome_file'], 60)} ({r['tipo']}, {r['dimensione'] // 1024} KiB)" for r in elenco]
        testo = await testo_per(interaction, "casesystem_prove_elenco", numero=numero, n=len(elenco)) + "\n" + "\n".join(righe)
        files, totale = [], 0
        for r in await moderation_repo.get_immagini_prova(guild_id, numero):
            totale += len(r["dati"])
            if totale <= MAX_BYTE_RISPOSTA:
                files.append(discord.File(io.BytesIO(r["dati"]), filename=f"prova_{r['id']}.png"))
        await interaction.followup.send(truncate_text(testo, 1900), files=files, ephemeral=True, allowed_mentions=discord.AllowedMentions.none())


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ProveCog(bot))
