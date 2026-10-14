"""
cogs/fun/fun_extra.py
=====================
Voci piccole di /fun (#131, FUN-023..048, 058..061): scegli, numero, testo
in stili, contenuti a caso, scherzi verso un utente, effetti sull'avatar.
Tutto SFW, nessuna rete. Sotto il gruppo esistente /fun (6 figli nuovi).
Funzioni coperte: SPEC §16 (16.1, 16.2, 16.8).
"""

from __future__ import annotations

import random

import discord
from discord import app_commands
from discord.ext import commands

from cogs.fun.entertainment import MODULE_FUN, EntertainmentCog
from core import fun_extra_logic as logica
from core import image_effects_logic as effetti
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.database import db

NESSUNA_MENZIONE = discord.AllowedMentions.none()

_CASUALI = {
    "preferiresti": ("🤔", logica.preferiresti),
    "argomento": ("💭", logica.argomento),
    "consiglio": ("💡", logica.consiglio),
    "oggetto-magico": ("✨", logica.oggetto_magico),
}
_EFFETTI = {
    "arcobaleno": ("arcobaleno.png", effetti.effetto_arcobaleno, False),
    "rip": ("rip.png", effetti.effetto_rip, True),
    "ricercato": ("ricercato.png", effetti.effetto_ricercato, True),
    "triggered": ("triggered.gif", effetti.effetto_triggered, False),
}


class FunExtraCog(CogConGruppi, commands.Cog):
    # Stessi controlli e stesso percorso immagini di EntertainmentCog.
    _allegato_accettabile = EntertainmentCog._allegato_accettabile
    _scarica_immagine = EntertainmentCog._scarica_immagine
    _rispondi_con_immagine = EntertainmentCog._rispondi_con_immagine

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._rng = random.Random()

    async def _modulo_attivo(self, interaction: discord.Interaction) -> bool:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return False
        if not await db.is_module_active_for_guild(interaction.guild.id, MODULE_FUN):
            await interaction.response.send_message(
                "Questo modulo non è attivo su questo server. "
                "Un amministratore può attivarlo con /admin setup attiva.",
                ephemeral=True,
            )
            return False
        return True

    async def _scrivi(self, interaction: discord.Interaction, testo: str, **kw) -> None:
        await interaction.response.send_message(
            testo[: logica.MAX_MESSAGGIO], allowed_mentions=NESSUNA_MENZIONE, **kw
        )

    @comando_di_gruppo("fun", nome="scegli", descrizione="Scelgo a caso tra le opzioni che scrivi.")
    @app_commands.describe(opzioni="Opzioni separate da virgola (da 2 a 20)")
    async def scegli(self, interaction: discord.Interaction, opzioni: app_commands.Range[str, 3, 500]) -> None:
        if not await self._modulo_attivo(interaction):
            return
        esito = logica.scegli_tra(opzioni, self._rng)
        if esito.errore:
            await self._scrivi(interaction, esito.errore, ephemeral=True)
            return
        await self._scrivi(interaction, f"🎯 Scelgo: **{esito.scelta}**")

    @comando_di_gruppo("fun", nome="numero", descrizione="Un numero a caso in un intervallo.")
    @app_commands.describe(minimo="Estremo più basso", massimo="Estremo più alto")
    async def numero(
        self,
        interaction: discord.Interaction,
        minimo: app_commands.Range[int, -1_000_000, 1_000_000] = 1,
        massimo: app_commands.Range[int, -1_000_000, 1_000_000] = 100,
    ) -> None:
        if not await self._modulo_attivo(interaction):
            return
        valore = logica.numero_casuale(minimo, massimo, self._rng)
        if valore is None:
            await self._scrivi(interaction, "Il minimo non può superare il massimo.", ephemeral=True)
            return
        await self._scrivi(interaction, f"🔢 Da {minimo} a {massimo}: **{valore}**")

    @comando_di_gruppo("fun", nome="testo", descrizione="Scrivi un testo in uno stile speciale.")
    @app_commands.describe(
        stile="Come trasformare il testo", testo="Il testo (massimo 500 caratteri)",
        separatore="Solo per lo stile Separato: carattere o emoji tra le parole",
    )
    @app_commands.choices(
        stile=[app_commands.Choice(name=n.replace("-", " ").capitalize(), value=n) for n in logica.STILI_TESTO]
    )
    async def testo(
        self,
        interaction: discord.Interaction,
        stile: app_commands.Choice[str],
        testo: app_commands.Range[str, 1, 500],
        separatore: app_commands.Range[str, 1, 10] = " ",
    ) -> None:
        if not await self._modulo_attivo(interaction):
            return
        await self._scrivi(interaction, logica.trasforma_testo(stile.value, testo, separatore) or "​")

    @comando_di_gruppo("fun", nome="casuale", descrizione="Preferiresti, argomento, consiglio, oggetto magico.")
    @app_commands.describe(tipo="Cosa vuoi")
    @app_commands.choices(
        tipo=[
            app_commands.Choice(name="Preferiresti…?", value="preferiresti"),
            app_commands.Choice(name="Argomento di conversazione", value="argomento"),
            app_commands.Choice(name="Consiglio", value="consiglio"),
            app_commands.Choice(name="Oggetto magico", value="oggetto-magico"),
        ]
    )
    async def casuale(self, interaction: discord.Interaction, tipo: app_commands.Choice[str]) -> None:
        if not await self._modulo_attivo(interaction):
            return
        emoji, genera = _CASUALI[tipo.value]
        await self._scrivi(interaction, f"{emoji} {genera(self._rng)}")

    @comando_di_gruppo("fun", nome="scherzo", descrizione="Uno scherzo innocuo verso un utente.")
    @app_commands.describe(
        tipo="Che scherzo", utente="Chi riceve lo scherzo",
        testo="Solo per Google: cosa cercare (massimo 100 caratteri)",
    )
    @app_commands.choices(
        tipo=[
            app_commands.Choice(name="Lancia un oggetto", value="lancia"),
            app_commands.Choice(name="Presa in giro", value="presa-in-giro"),
            app_commands.Choice(name="Cercalo su Google", value="google"),
        ]
    )
    async def scherzo(
        self,
        interaction: discord.Interaction,
        tipo: app_commands.Choice[str],
        utente: discord.Member,
        testo: app_commands.Range[str, 1, 100] | None = None,
    ) -> None:
        if not await self._modulo_attivo(interaction):
            return
        if tipo.value == "google":
            if not testo:
                await self._scrivi(interaction, "Scrivi cosa cercare nel campo `testo`.", ephemeral=True)
                return
            frase = f"🔎 {utente.mention}, forse ti serve questo: <{logica.google_link(testo)}>"
        elif tipo.value == "lancia":
            frase = f"🎯 {interaction.user.mention} lancia {logica.lancia_oggetto(self._rng)} a {utente.mention}!"
        else:
            frase = f"😏 {logica.presa_in_giro(self._rng, utente.mention)}"
        await self._scrivi(interaction, frase)

    @comando_di_gruppo("fun", nome="effetto", descrizione="Effetto sull'avatar: arcobaleno, R.I.P., ricercato, triggered.")
    @app_commands.describe(
        tipo="Che effetto", image="Immagine (facoltativa: senza, usa l'avatar)",
        utente="Usa l'avatar di questo utente", nome="Nome sul manifesto o sulla lapide (massimo 40)",
    )
    @app_commands.choices(
        tipo=[
            app_commands.Choice(name="Arcobaleno", value="arcobaleno"),
            app_commands.Choice(name="Lapide R.I.P.", value="rip"),
            app_commands.Choice(name="Ricercato", value="ricercato"),
            app_commands.Choice(name="Triggered (GIF)", value="triggered"),
        ]
    )
    async def effetto(
        self,
        interaction: discord.Interaction,
        tipo: app_commands.Choice[str],
        image: discord.Attachment | None = None,
        utente: discord.Member | None = None,
        nome: app_commands.Range[str, 1, effetti.MAX_NOME] | None = None,
    ) -> None:
        if not await self._modulo_attivo(interaction):
            return
        nome_file, funzione, vuole_nome = _EFFETTI[tipo.value]
        argomenti = ()
        if vuole_nome:
            argomenti = (nome or (utente or interaction.user).display_name,)
        await self._rispondi_con_immagine(interaction, image, utente, nome_file, funzione, *argomenti)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(FunExtraCog(bot))
