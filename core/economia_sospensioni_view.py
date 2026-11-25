"""
core/economia_sospensioni_view.py
=================================
Ciò che vede chi è sospeso dal gioco (ECO-160): il motivo e il bottone «Chiedi una revisione». Il bottone apre una
finestra con il testo (massimo 500 caratteri) e la richiesta arriva allo staff nel canale dei casi di moderazione,
con le istruzioni per decidere. Una richiesta sola per sospensione.
Funzioni coperte: ECO-160
Dipende da: core/economia_sospensioni.py, cogs/moderation/_shared.py (canale dei casi)
"""

from __future__ import annotations

from core.comandi_diretti import percorso_vero

import discord

from core import economia_sospensioni as es
from core.i18n import testo_per
from core.ui_base import BaseModal, BaseView

NESSUNA_MENZIONE = discord.AllowedMentions.none()


class ModuloRevisione(BaseModal, title="Chiedi una revisione"):
    testo = discord.ui.TextInput(
        label="Perché la sospensione va tolta?", style=discord.TextStyle.paragraph, min_length=5, max_length=es.MAX_APPELLO
    )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        if guild is None or not await es.apri_appello(guild.id, interaction.user.id, str(self.testo)):
            await interaction.followup.send(await testo_per(interaction, "sospensione_appello_no"), ephemeral=True)
            return
        from cogs.moderation._shared import post_to_mod_log  # import tardivo: la moderazione non dipende da qui

        embed = discord.Embed(
            title="Richiesta di revisione: sospensione dal gioco",
            description=discord.utils.escape_mentions(str(self.testo))[:3500],
            color=discord.Color.orange(),
        )
        embed.add_field(name="Utente", value=f"<@{interaction.user.id}> ({interaction.user.id})", inline=False)
        embed.add_field(
            name="Per decidere",
            value=f"`/admin-giochi sospensione azione:accogli utente:@{interaction.user.id}` o `azione:respingi`",
            inline=False,
        )
        await post_to_mod_log(guild, embed)
        await interaction.followup.send(await testo_per(interaction, "sospensione_appello_inviato"), ephemeral=True)


class VistaSospeso(BaseView):
    def __init__(self, puo_chiedere: bool, etichetta: str) -> None:
        super().__init__(timeout=600)
        if puo_chiedere:
            bottone = discord.ui.Button(label=etichetta[:80], style=discord.ButtonStyle.secondary)
            bottone.callback = self._premuto
            self.add_item(bottone)

    async def _premuto(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(ModuloRevisione())


async def rifiuta_se_sospeso(interaction: discord.Interaction) -> bool:
    """Vero (dopo aver risposto) se la persona è sospesa e il comando è di gioco. Mai solleva: un guasto lascia passare."""
    try:
        if interaction.guild is None or interaction.command is None:
            return False
        if not es.e_di_gioco(percorso_vero(interaction.command)):
            return False
        sosp = await es.attiva_in_cache(interaction.guild.id, interaction.user.id)
        if sosp is None:
            return False
        scade = f" Fino a {discord.utils.format_dt(sosp['fino_a'], 'f')}." if sosp["fino_a"] else ""
        stato = {"aperto": "sospensione_revisione_aperta", "respinto": "sospensione_revisione_respinta"}.get(sosp["appello_stato"])
        testo = await testo_per(interaction, "sospensione_avviso", motivo=discord.utils.escape_markdown(sosp["motivo"]), scade=scade)
        if stato:
            testo += "\n" + await testo_per(interaction, stato)
        vista = VistaSospeso(sosp["appello_stato"] == "nessuno", await testo_per(interaction, "sospensione_bottone"))
        await interaction.response.send_message(testo, view=vista, ephemeral=True, allowed_mentions=NESSUNA_MENZIONE)
        return True
    except discord.HTTPException:
        return True
    except Exception:
        return False
