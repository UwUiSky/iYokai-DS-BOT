"""
cogs/user_app/risposte.py
=========================
Risposte salvate personali di iYokai App (SPEC §B.5): `/risposta salva|usa|elenco|rimuovi` e, sul menu del
messaggio, «Salva come risposta pronta». La risposta esce come messaggio dell'app (testo o embed), mai a nome
della persona. Si carica solo sul client dell'app (core/user_app_bot.py).
Funzioni coperte: SPEC §B.5 (NF-36, #107)
Dipende da: core/user_app_risposte.py, core/repositories/user_app_repo.py
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from core.i18n import lingua_interazione, t, testo_per
from core.repositories.user_app_repo import MAX_RISPOSTE, user_app_repo
from core.ui_base import BaseModal
from core.user_app_bot import e_istanza_app
from core.user_app_risposte import (
    MAX_TESTO,
    MAX_TITOLO,
    colore_intero,
    e_embed,
    immagine_valida,
    normalizza_nome,
)
from core.user_app_strumenti import ErroreStrumento

INSTALLAZIONE = app_commands.AppInstallationType(guild=False, user=True)
OVUNQUE = app_commands.AppCommandContext(guild=True, dm_channel=True, private_channel=True)
NESSUNA_MENZIONE = discord.AllowedMentions.none()
NOME_MENU = "Salva come risposta pronta"


async def _completa_nomi(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    nomi = await user_app_repo.nomi_risposte(interaction.user.id, current.strip().lower(), 25)
    return [app_commands.Choice(name=n, value=n) for n in nomi]


async def salva(
    interaction: discord.Interaction, nome: str, testo: str, titolo: str | None = None, colore: str | None = None,
    immagine: str | None = None,
) -> None:
    """Controlla, salva e risponde (una volta sola, in privato)."""
    try:
        nome = normalizza_nome(nome)
        colore_n = colore_intero(colore)
        immagine = immagine_valida(immagine)
    except ErroreStrumento as errore:
        await interaction.response.send_message(await testo_per(interaction, errore.chiave), ephemeral=True)
        return
    esito = await user_app_repo.salva_risposta(
        interaction.user.id, nome, testo[:MAX_TESTO], (titolo or "").strip()[:MAX_TITOLO] or None, colore_n, immagine
    )
    chiave = {"nuova": "app_risposta_salvata", "aggiornata": "app_risposta_aggiornata", "piena": "app_risposta_piena"}[esito]
    await interaction.response.send_message(
        await testo_per(interaction, chiave, nome=nome, massimo=MAX_RISPOSTE), ephemeral=True
    )


class SalvaModal(BaseModal):
    def __init__(self, testo: str, lingua: str = "it") -> None:
        super().__init__(title=t("app_menu_salva_risposta", lingua)[:45])
        self.testo = testo
        self.nome = discord.ui.TextInput(label=t("app_risposta_nome", lingua)[:45], min_length=1, max_length=32)
        self.add_item(self.nome)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await salva(interaction, self.nome.value, self.testo)


class RisposteCog(commands.Cog):
    risposta = app_commands.Group(
        name="risposta", description="Le tue risposte pronte, da usare in ogni server e in DM.",
        allowed_installs=INSTALLAZIONE, allowed_contexts=OVUNQUE,
    )

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._menu = app_commands.ContextMenu(
            name=NOME_MENU, callback=self.menu_salva, allowed_installs=INSTALLAZIONE, allowed_contexts=OVUNQUE
        )
        bot.tree.add_command(self._menu)

    async def cog_unload(self) -> None:
        self.bot.tree.remove_command(self._menu.name, type=self._menu.type)

    @risposta.command(name="salva", description="Salva una risposta pronta (testo, o embed con titolo, colore e immagine).")
    @app_commands.describe(
        nome="Il nome per richiamarla (lettere, numeri, - e _)", testo="Il testo della risposta",
        titolo="Titolo dell'embed (facoltativo)", colore="Colore dell'embed, es. #ff8800 (facoltativo)",
        immagine="Indirizzo https di un'immagine per l'embed (facoltativo)",
    )
    async def salva_cmd(
        self, interaction: discord.Interaction, nome: app_commands.Range[str, 1, 32],
        testo: app_commands.Range[str, 1, MAX_TESTO], titolo: app_commands.Range[str, 0, MAX_TITOLO] = "",
        colore: app_commands.Range[str, 0, 20] = "", immagine: app_commands.Range[str, 0, 300] = "",
    ) -> None:
        await salva(interaction, nome, testo, titolo, colore, immagine)

    @risposta.command(name="usa", description="Scrive una tua risposta pronta come risposta dell'app.")
    @app_commands.describe(nome="Il nome della risposta", privata="Solo tu la vedi (di base la vedono tutti)")
    @app_commands.autocomplete(nome=_completa_nomi)
    async def usa(
        self, interaction: discord.Interaction, nome: app_commands.Range[str, 1, 32], privata: bool = False
    ) -> None:
        riga = await user_app_repo.risposta(interaction.user.id, nome.strip().lower())
        if riga is None:
            await interaction.response.send_message(await testo_per(interaction, "app_risposta_non_trovata", nome=nome), ephemeral=True)
            return
        if e_embed(riga["titolo"], riga["colore"], riga["immagine_url"]):
            embed = discord.Embed(
                title=riga["titolo"], description=riga["testo"], color=riga["colore"] if riga["colore"] is not None else discord.Color.blurple()
            )
            if riga["immagine_url"]:
                embed.set_image(url=riga["immagine_url"])
            await interaction.response.send_message(embed=embed, ephemeral=privata, allowed_mentions=NESSUNA_MENZIONE)
            return
        await interaction.response.send_message(riga["testo"], ephemeral=privata, allowed_mentions=NESSUNA_MENZIONE)

    @risposta.command(name="elenco", description="Le tue risposte pronte.")
    async def elenco(self, interaction: discord.Interaction) -> None:
        nomi = await user_app_repo.nomi_risposte(interaction.user.id, "", MAX_RISPOSTE)
        lingua = await lingua_interazione(interaction)
        if not nomi:
            await interaction.response.send_message(t("app_risposta_nessuna", lingua), ephemeral=True)
            return
        embed = discord.Embed(
            title=t("app_risposta_titolo", lingua), description=", ".join(f"`{n}`" for n in nomi)[:4000],
            color=discord.Color.blurple(),
        )
        embed.set_footer(text=f"{len(nomi)}/{MAX_RISPOSTE}")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @risposta.command(name="rimuovi", description="Toglie una risposta pronta.")
    @app_commands.describe(nome="Il nome della risposta")
    @app_commands.autocomplete(nome=_completa_nomi)
    async def rimuovi(self, interaction: discord.Interaction, nome: app_commands.Range[str, 1, 32]) -> None:
        chiave = "app_risposta_tolta" if await user_app_repo.rimuovi_risposta(interaction.user.id, nome.strip().lower()) else "app_risposta_non_trovata"
        await interaction.response.send_message(await testo_per(interaction, chiave, nome=nome), ephemeral=True)

    async def menu_salva(self, interaction: discord.Interaction, messaggio: discord.Message) -> None:
        testo = messaggio.content or next((e.description for e in messaggio.embeds if e.description), "")
        if not testo.strip():
            await interaction.response.send_message(await testo_per(interaction, "app_msg_senza_testo"), ephemeral=True)
            return
        await interaction.response.send_modal(SalvaModal(testo[:MAX_TESTO], await lingua_interazione(interaction)))


async def setup(bot: commands.Bot) -> None:
    """Solo sul client dell'app: il bot principale non riceve questi comandi."""
    if e_istanza_app(bot):
        await bot.add_cog(RisposteCog(bot))
