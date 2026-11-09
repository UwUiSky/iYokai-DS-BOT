"""
cogs/utility/lingua.py
======================
`/utility lingua`: ogni utente sceglie la sua lingua per le risposte che vede solo lui. Quelle
pubbliche seguono la lingua del server (`/admin-bot lingua set`). Il bottone «Chiedi una lingua» apre
un modulo e manda la richiesta all'owner (`core/lingua_richieste.py`, una al giorno per utente).
Funzioni coperte: SPEC §21 (NF-06, #77, D58). Dati: tabella `user_language` (0130, registro dei dati).
Nessun controllo di modulo: è una preferenza personale, non una funzione del server.
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from core.command_groups import CogConGruppi, comando_di_gruppo
from core import lingua_richieste as richieste
from core.orari_logic import MAX_FUSO, cerca_fusi, fuso_esiste
from core.repositories.utente_fuso_repo import utente_fuso_repo
from core.i18n import imposta_lingua_utente, lingua_interazione, lingua_server, lingua_utente, t
from core.ui_base import BaseModal, BaseView

_TESTO_ESITO = {
    richieste.Esito.INVIATA: "lingua_richiesta_ok",
    richieste.Esito.LIMITE: "lingua_richiesta_limite",
    richieste.Esito.NOME_VUOTO: "lingua_richiesta_nome_vuoto",
    richieste.Esito.NON_INVIATA: "lingua_richiesta_non_inviata",
}


class RichiestaLinguaModal(BaseModal):
    def __init__(self, bot: commands.Bot, lingua: str) -> None:
        super().__init__(title=t("lingua_richiesta_titolo", lingua)[:45], timeout=300)
        self.bot = bot
        self.lingua = lingua
        self.nome = discord.ui.TextInput(
            label=t("lingua_richiesta_nome_label", lingua)[:45],
            placeholder=t("lingua_richiesta_nome_segnaposto", lingua)[:100],
            max_length=richieste.MAX_NOME_LINGUA,
        )
        self.nota = discord.ui.TextInput(
            label=t("lingua_richiesta_nota_label", lingua)[:45],
            style=discord.TextStyle.paragraph,
            required=False,
            max_length=richieste.MAX_NOTA,
        )
        self.add_item(self.nome)
        self.add_item(self.nota)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)  # il DM all'owner può durare più di 3 secondi
        esito = await richieste.invia_richiesta(
            self.bot, interaction.user, interaction.guild, self.nome.value, self.nota.value
        )
        await interaction.followup.send(t(_TESTO_ESITO[esito], self.lingua), ephemeral=True)


class ChiediLinguaView(BaseView):
    def __init__(self, bot: commands.Bot, lingua: str) -> None:
        super().__init__(timeout=300)
        self.bot = bot
        self.lingua = lingua
        bottone = discord.ui.Button(label=t("lingua_richiesta_bottone", lingua)[:80], style=discord.ButtonStyle.secondary)
        bottone.callback = self._apri
        self.add_item(bottone)

    async def _apri(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(RichiestaLinguaModal(self.bot, self.lingua))


async def _completa_fuso(interaction: discord.Interaction, corrente: str) -> list[app_commands.Choice[str]]:
    return [app_commands.Choice(name=n, value=n) for n in cerca_fusi(corrente)]


class LinguaCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @comando_di_gruppo(
        "utility",
        nome="lingua",
        descrizione="Mostra o cambia la tua lingua personale (italiano o inglese).",
    )
    @app_commands.describe(
        lingua="Lingua per le risposte che vedi solo tu; vuoto = mostra quella attuale",
        fuso="Il tuo fuso orario (scrivi per cercare, es. Europe/Rome); «nessuno» lo toglie",
    )
    @app_commands.autocomplete(fuso=_completa_fuso)
    @app_commands.choices(
        lingua=[
            app_commands.Choice(name="Italiano", value="it"),
            app_commands.Choice(name="English", value="en"),
            app_commands.Choice(name="Lingua del server / Server language", value="server"),
        ]
    )
    async def lingua(
        self,
        interaction: discord.Interaction,
        lingua: app_commands.Choice[str] | None = None,
        fuso: app_commands.Range[str, 1, MAX_FUSO] | None = None,
    ) -> None:
        server = await lingua_server(interaction.guild.id if interaction.guild else None)
        if fuso is not None:
            await self._imposta_fuso(interaction, fuso, lingua)
            return
        if lingua is None:
            mia = await lingua_utente(interaction.user.id)
            testo = (
                t("lingua_utente_attuale", mia, lingua=mia, server=server)
                if mia
                else t("lingua_utente_nessuna", server, server=server)
            )
        else:
            salvata = await imposta_lingua_utente(interaction.user.id, lingua.value)
            testo = (
                t("lingua_utente_impostata", salvata, lingua=salvata)
                if salvata
                else t("lingua_utente_azzerata", server)
            )
        vista = ChiediLinguaView(self.bot, await lingua_interazione(interaction))
        await interaction.response.send_message(testo, view=vista, ephemeral=True)


    async def _imposta_fuso(self, interaction: discord.Interaction, fuso: str, lingua) -> None:
        """Salva (o toglie) il fuso. Se c'è anche la lingua la cambia come sempre."""
        if lingua is not None:
            await imposta_lingua_utente(interaction.user.id, lingua.value)
        lg = await lingua_interazione(interaction)
        if fuso.strip().casefold() in ("nessuno", "none"):
            await utente_fuso_repo.remove(interaction.user.id)
            testo = t("fuso_tolto", lg)
        elif not fuso_esiste(fuso.strip()):
            testo = t("fuso_sconosciuto", lg)
        else:
            await utente_fuso_repo.set(interaction.user.id, fuso.strip())
            testo = t("fuso_impostato", lg, fuso=fuso.strip())
        await interaction.response.send_message(testo, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(LinguaCog(bot))
