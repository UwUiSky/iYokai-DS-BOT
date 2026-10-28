"""
cogs/user_app/strumenti.py
==========================
Strumenti personali di iYokai App (SPEC §B.3, §B.4): `/strumenti calcola|converti|fuso|colore|qr`,
`/note aggiungi|elenco|rimuovi` (note e liste) e, sul menu «App» di un utente, «Stato rete iYokai»
(solo per se stessi, risposta privata). Ogni comando risponde una volta sola, in privato. Si carica solo
sul client dell'app (core/user_app_bot.py): sul bot principale `setup` non fa nulla.
Funzioni coperte: SPEC §B.3, §B.4 (NF-36, #107)
Dipende da: core/user_app_strumenti.py, core/repositories/user_app_note_repo.py
"""

from __future__ import annotations

import io

import discord
from discord import app_commands
from discord.ext import commands

from core.i18n import lingua_interazione, t, testo_per
from core.repositories.global_ban_repo import global_ban_repo
from core.repositories.user_app_note_repo import MAX_VOCI_PER_UTENTE, user_app_note_repo
from core.user_app_bot import e_istanza_app
from core.user_app_strumenti import (
    UNITA_ELENCO,
    ErroreStrumento,
    calcola,
    converti,
    converti_ora,
    formatta_numero,
    immagine_colore,
    leggi_colore,
    qr_png,
    zone_che_iniziano,
)

INSTALLAZIONE = app_commands.AppInstallationType(guild=False, user=True)
OVUNQUE = app_commands.AppCommandContext(guild=True, dm_channel=True, private_channel=True)
MAX_LISTA = 30
MAX_VOCE = 500


async def _completa_zone(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    return [app_commands.Choice(name=z, value=z) for z in zone_che_iniziano(current)]


async def _completa_unita(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    return [app_commands.Choice(name=u, value=u) for u in UNITA_ELENCO if current.lower() in u][:25]


class StrumentiCog(commands.Cog):
    strumenti = app_commands.Group(
        name="strumenti", description="Calcolatrice, conversioni, fusi orari, colori e codice QR.",
        allowed_installs=INSTALLAZIONE, allowed_contexts=OVUNQUE,
    )
    note = app_commands.Group(
        name="note", description="Le tue note e le tue liste, in ogni server e in DM.",
        allowed_installs=INSTALLAZIONE, allowed_contexts=OVUNQUE,
    )

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._menu = app_commands.ContextMenu(
            name="Stato rete iYokai", callback=self.menu_stato_rete,
            allowed_installs=INSTALLAZIONE, allowed_contexts=OVUNQUE,
        )
        bot.tree.add_command(self._menu)

    async def cog_unload(self) -> None:
        self.bot.tree.remove_command(self._menu.name, type=self._menu.type)

    async def _errore(self, interaction: discord.Interaction, errore: ErroreStrumento) -> None:
        await interaction.response.send_message(await testo_per(interaction, errore.chiave), ephemeral=True)

    # ---------------------------------------------------------------- strumenti
    @strumenti.command(name="calcola", description="Calcola un'espressione, es. (2+3)*4 o sqrt(16).")
    @app_commands.describe(espressione="Numeri, + - * / ** % ( ), sqrt, abs, round, pi")
    async def calcola(self, interaction: discord.Interaction, espressione: app_commands.Range[str, 1, 100]) -> None:
        try:
            risultato = calcola(espressione)
        except ErroreStrumento as errore:
            await self._errore(interaction, errore)
            return
        await interaction.response.send_message(
            await testo_per(interaction, "app_calc_risultato", espressione=espressione.replace("`", "'"), risultato=risultato),
            ephemeral=True,
        )

    @strumenti.command(name="converti", description="Converte lunghezze, pesi, volumi, velocità, dati e temperature.")
    @app_commands.describe(valore="Il numero da convertire", da="Unità di partenza, es. km", a="Unità di arrivo, es. mi")
    @app_commands.autocomplete(da=_completa_unita, a=_completa_unita)
    async def converti(
        self, interaction: discord.Interaction, valore: app_commands.Range[float, -1e12, 1e12],
        da: app_commands.Range[str, 1, 10], a: app_commands.Range[str, 1, 10],
    ) -> None:
        try:
            risultato = converti(valore, da, a)
        except ErroreStrumento as errore:
            await self._errore(interaction, errore)
            return
        await interaction.response.send_message(
            await testo_per(
                interaction, "app_conv_risultato", valore=formatta_numero(valore), da=da.lower(),
                risultato=formatta_numero(risultato), a=a.lower(),
            ),
            ephemeral=True,
        )

    @strumenti.command(name="fuso", description="Che ora è in un altro fuso orario.")
    @app_commands.describe(
        a="Fuso di arrivo, es. Asia/Tokyo", da="Fuso di partenza (vuoto: UTC)", ora="Ora di oggi nel fuso di partenza, HH:MM (vuoto: adesso)",
    )
    @app_commands.autocomplete(a=_completa_zone, da=_completa_zone)
    async def fuso(
        self, interaction: discord.Interaction, a: app_commands.Range[str, 1, 40],
        da: app_commands.Range[str, 1, 40] = "UTC", ora: app_commands.Range[str, 3, 5] | None = None,
    ) -> None:
        try:
            origine, arrivo = converti_ora(ora, da, a)
        except ErroreStrumento as errore:
            await self._errore(interaction, errore)
            return
        await interaction.response.send_message(
            await testo_per(
                interaction, "app_fuso_risultato", ora_da=origine.strftime("%H:%M"), zona_da=da,
                ora_a=arrivo.strftime("%H:%M"), zona_a=a, giorno=arrivo.strftime("%d/%m/%Y"),
            ),
            ephemeral=True,
        )

    @strumenti.command(name="colore", description="Mostra un colore in HEX, RGB e HSL.")
    @app_commands.describe(codice="Es. #ff8800, f80 o rgb(255,136,0)")
    async def colore(self, interaction: discord.Interaction, codice: app_commands.Range[str, 1, 30]) -> None:
        try:
            colore = leggi_colore(codice)
        except ErroreStrumento as errore:
            await self._errore(interaction, errore)
            return
        embed = discord.Embed(title=colore.hex, description=f"{colore.rgb}\n{colore.hsl}", color=colore.intero)
        embed.set_thumbnail(url="attachment://colore.png")
        await interaction.response.send_message(
            embed=embed, file=discord.File(io.BytesIO(immagine_colore(colore)), "colore.png"), ephemeral=True
        )

    @strumenti.command(name="qr", description="Crea un codice QR da un testo o un link.")
    @app_commands.describe(testo="Il testo o il link (fino a 300 caratteri)")
    async def qr(self, interaction: discord.Interaction, testo: app_commands.Range[str, 1, 300]) -> None:
        try:
            png = qr_png(testo)
        except ErroreStrumento as errore:
            await self._errore(interaction, errore)
            return
        await interaction.response.send_message(file=discord.File(io.BytesIO(png), "qr.png"), ephemeral=True)

    # ---------------------------------------------------------------- note e liste
    @note.command(name="aggiungi", description="Aggiunge una nota, o una voce a una lista.")
    @app_commands.describe(testo="Cosa scrivere", lista="Il nome della lista (vuoto: le note)")
    async def aggiungi(
        self, interaction: discord.Interaction, testo: app_commands.Range[str, 1, MAX_VOCE],
        lista: app_commands.Range[str, 1, MAX_LISTA] | None = None,
    ) -> None:
        numero = await user_app_note_repo.aggiungi(interaction.user.id, (lista or "").strip().lower(), testo)
        chiave = "app_note_piene" if numero is None else "app_note_aggiunta"
        await interaction.response.send_message(
            await testo_per(interaction, chiave, numero=numero, massimo=MAX_VOCI_PER_UTENTE), ephemeral=True
        )

    @note.command(name="elenco", description="Mostra le tue note, o una lista.")
    @app_commands.describe(lista="Il nome della lista (vuoto: le note e l'elenco delle liste)")
    async def elenco(self, interaction: discord.Interaction, lista: app_commands.Range[str, 1, MAX_LISTA] | None = None) -> None:
        nome = (lista or "").strip().lower()
        voci = await user_app_note_repo.elenco(interaction.user.id, nome)
        lingua = await lingua_interazione(interaction)
        righe = [f"`{v['id']}` · {v['testo'][:300]}" for v in voci]
        titolo = t("app_note_titolo_lista", lingua, lista=nome) if nome else t("app_note_titolo", lingua)
        corpo = "\n".join(righe) or t("app_note_nessuna", lingua)
        if not nome:
            altre = [r["lista"] for r in await user_app_note_repo.liste(interaction.user.id) if r["lista"]]
            if altre:
                corpo += "\n\n" + t("app_note_liste", lingua, elenco=", ".join(f"`{a}`" for a in altre[:25]))
        await interaction.response.send_message(
            embed=discord.Embed(title=titolo[:256], description=corpo[:4000], color=discord.Color.blurple()), ephemeral=True
        )

    @note.command(name="rimuovi", description="Toglie una nota o una voce di lista.")
    @app_commands.describe(numero="Il numero (da /note elenco)")
    async def rimuovi(self, interaction: discord.Interaction, numero: app_commands.Range[int, 1, 2**53 - 1]) -> None:
        fatto = await user_app_note_repo.rimuovi(interaction.user.id, numero)
        await interaction.response.send_message(
            await testo_per(interaction, "app_note_rimossa" if fatto else "app_note_non_trovata", numero=numero),
            ephemeral=True,
        )

    # ---------------------------------------------------------------- stato nella rete di sicurezza
    async def menu_stato_rete(self, interaction: discord.Interaction, utente: discord.User) -> None:
        """Solo per se stessi: chi è in lista non deve poterlo scoprire sugli altri."""
        if utente.id != interaction.user.id:
            await interaction.response.send_message(await testo_per(interaction, "app_stato_solo_tuo"), ephemeral=True)
            return
        server, primo, ultimo = await global_ban_repo.network_summary(utente.id)
        if not server:
            testo = await testo_per(interaction, "app_stato_nessuno")
        else:
            testo = await testo_per(
                interaction, "app_stato_presente", server=server,
                primo=discord.utils.format_dt(primo, "D"), ultimo=discord.utils.format_dt(ultimo, "D"),
            )
        await interaction.response.send_message(testo, ephemeral=True, allowed_mentions=discord.AllowedMentions.none())


async def setup(bot: commands.Bot) -> None:
    """Solo sul client dell'app: il bot principale non riceve questi comandi."""
    if not e_istanza_app(bot):
        return
    await bot.add_cog(StrumentiCog(bot))
