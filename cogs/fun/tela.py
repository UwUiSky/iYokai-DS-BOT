"""
cogs/fun/tela.py
================
La tela di pixel del server (/giochi tela ...): ognuno colora un pixel ogni tanto (di base ogni 5 minuti; chi vuole può pagare
monete per saltare la pausa), `/giochi tela vedi` disegna la tela o una zona ingrandita fuori dal ciclo principale. Per lo
staff (FUN-014): `/admin-giochi tela azzera|togli-utente|blocca|sblocca|impostazioni`. La pagina pubblica in sola
lettura è `/tela/<server>` del pannello web (core/web_panel_tela.py), solo se il server la accende.
Funzioni coperte: FUN-013, FUN-014
Dipende da: core/tela_logic.py, core/tela_image.py, core/repositories/tela_repo.py
"""

from __future__ import annotations

import io
import logging

import discord
from discord import app_commands
from discord.ext import commands

from core import tela_logic as tl
from core.config import config
from core.command_access import Livello, richiedi
from core.command_groups import CogConGruppi, comando_di_gruppo, SOTTOGRUPPI
from core.database import db
from core.i18n import testo_per
from core.repositories.tela_repo import Esito, tela_repo
from core.safe_image import run_image_task
from core.tela_image import disegna

logger = logging.getLogger("iyokai.tela")
NESSUNA_MENZIONE = discord.AllowedMentions.none()
SG_TELA_ADMIN = ("tela", "Tela di pixel: moderazione e impostazioni")
MODULO = "fun"


def indirizzo_pubblico(guild_id: int) -> str | None:
    base = (config.WEB_PANEL_PUBLIC_URL or "").rstrip("/")
    return f"{base}/tela/{guild_id}" if base else None


async def _completa_colori(interaction: discord.Interaction, digitato: str) -> list[app_commands.Choice[int]]:
    d = digitato.lower().strip()
    voci = []
    for i in range(tl.NUMERO_COLORI):
        nome = await testo_per(interaction, f"tela_c_{i}", pubblica=True)
        if not d or d in nome.lower() or d == str(i):
            voci.append(app_commands.Choice(name=f"{i} · {nome}"[:100], value=i))
    return voci[:25]


class TelaCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def _pronto(self, interaction: discord.Interaction) -> bool:
        if interaction.guild is None:
            await interaction.response.send_message(await testo_per(interaction, "guild_only_command"), ephemeral=True)
            return False
        if not await db.is_module_active_for_guild(interaction.guild.id, MODULO):
            await interaction.response.send_message(await testo_per(interaction, "ping_questo_modulo_non_attivo_su"), ephemeral=True)
            return False
        return True

    # ---------------------------------------------------------------- per tutti
    @comando_di_gruppo("giochi", nome="vedi", descrizione="Guarda la tela di pixel del server, o una zona ingrandita.", sottogruppo=SOTTOGRUPPI["giochi tela"])
    @app_commands.describe(x="Colonna al centro della zona (0-99)", y="Riga al centro della zona (0-99)", zoom="1 = tutta la tela, 4 = zona piccolissima")
    async def vedi(self, interaction: discord.Interaction, x: app_commands.Range[int, 0, 99] = 50, y: app_commands.Range[int, 0, 99] = 50,
                   zoom: app_commands.Range[int, 1, 4] = 1) -> None:
        if not await self._pronto(interaction):
            return
        await interaction.response.defer()
        x0, y0, lato = tl.finestra(x, y, zoom)
        caselle = await tela_repo.caselle(interaction.guild.id, x0, y0, lato)
        png = await run_image_task(disegna, caselle, x0, y0, lato)  # Pillow fuori dal ciclo principale
        testo = await testo_per(interaction, "tela_vedi", pubblica=True, x0=x0, y0=y0, x1=x0 + lato - 1, y1=y0 + lato - 1, n=await tela_repo.conta(interaction.guild.id))
        if (await tela_repo.impostazioni(interaction.guild.id)).pubblica and (link := indirizzo_pubblico(interaction.guild.id)):
            testo += "\n" + await testo_per(interaction, "tela_link", pubblica=True, link=link)
        await interaction.followup.send(testo, file=discord.File(io.BytesIO(png), filename="tela.png"), allowed_mentions=NESSUNA_MENZIONE)

    @comando_di_gruppo("giochi", nome="colora", descrizione="Colora un pixel della tela (c'è una pausa tra un pixel e l'altro).", sottogruppo=SOTTOGRUPPI["giochi tela"])
    @app_commands.describe(x="Colonna (0-99)", y="Riga (0-99)", colore="Il colore (0-15)", accorcia="Se sei in pausa, paga monete per saltarla")
    @app_commands.autocomplete(colore=_completa_colori)
    async def colora(self, interaction: discord.Interaction, x: app_commands.Range[int, 0, 99], y: app_commands.Range[int, 0, 99],
                     colore: app_commands.Range[int, 0, 15], accorcia: bool = False) -> None:
        if not await self._pronto(interaction):
            return
        if accorcia and not await db.is_module_active_for_guild(interaction.guild.id, "leveling"):
            await interaction.response.send_message(await testo_per(interaction, "ping_questo_modulo_non_attivo_su"), ephemeral=True)
            return
        r = await tela_repo.colora(interaction.guild.id, interaction.user.id, x, y, colore, accorcia)
        nome = await testo_per(interaction, f"tela_c_{colore}")
        if r.esito is Esito.OK:
            chiave = "tela_ok_pagato" if r.costo else "tela_ok"
        else:
            chiave = {Esito.PAUSA: "tela_pausa", Esito.POCHE: "tela_poche", Esito.BLOCCATO: "tela_bloccato"}[r.esito]
        await interaction.response.send_message(
            await testo_per(interaction, chiave, x=x, y=y, colore=nome, attesa=tl.formatta_attesa(r.resta), costo=r.costo),
            ephemeral=True)

    @comando_di_gruppo("giochi", nome="pixel", descrizione="Chi ha colorato un pixel e quando.", sottogruppo=SOTTOGRUPPI["giochi tela"])
    @app_commands.describe(x="Colonna (0-99)", y="Riga (0-99)")
    async def pixel(self, interaction: discord.Interaction, x: app_commands.Range[int, 0, 99], y: app_commands.Range[int, 0, 99]) -> None:
        if not await self._pronto(interaction):
            return
        p = await tela_repo.pixel(interaction.guild.id, x, y)
        if p is None:
            await interaction.response.send_message(await testo_per(interaction, "tela_pixel_vuoto", x=x, y=y), ephemeral=True)
            return
        autore = f"<@{p.user_id}>" if p.user_id else await testo_per(interaction, "tela_autore_ignoto", pubblica=True)
        await interaction.response.send_message(
            await testo_per(interaction, "tela_pixel", pubblica=True, x=x, y=y, colore=await testo_per(interaction, f"tela_c_{p.colore}", pubblica=True),
                            chi=autore, quando=f"<t:{int(p.messo_il.timestamp())}:R>"),
            allowed_mentions=NESSUNA_MENZIONE)

    @comando_di_gruppo("giochi", nome="stato", descrizione="La tua pausa, i tuoi pixel e quanto costa saltarla.", sottogruppo=SOTTOGRUPPI["giochi tela"])
    async def stato(self, interaction: discord.Interaction) -> None:
        if not await self._pronto(interaction):
            return
        resta, bloccato, messi = await tela_repo.attesa(interaction.guild.id, interaction.user.id)
        imp = await tela_repo.impostazioni(interaction.guild.id)
        if bloccato:
            testo = await testo_per(interaction, "tela_bloccato")
        else:
            testo = await testo_per(interaction, "tela_stato", attesa=tl.formatta_attesa(resta), messi=messi, pausa=imp.pausa_secondi // 60 or 1,
                                    costo=tl.costo_accorciare(resta, imp.costo_minuto))
        await interaction.response.send_message(testo, ephemeral=True)

    # ---------------------------------------------------------------- staff (FUN-014)
    @comando_di_gruppo("admin-giochi", nome="azzera", descrizione="Svuota tutta la tela di pixel del server.", sottogruppo=SG_TELA_ADMIN)
    @app_commands.describe(conferma="Metti «sì» per svuotare davvero la tela")
    @richiedi(Livello.ADMIN)
    async def azzera(self, interaction: discord.Interaction, conferma: bool = False) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(await testo_per(interaction, "guild_only_command"), ephemeral=True)
            return
        if not conferma:
            await interaction.response.send_message(await testo_per(interaction, "tela_azzera_conferma"), ephemeral=True)
            return
        n = await tela_repo.azzera(interaction.guild.id)
        await interaction.response.send_message(await testo_per(interaction, "tela_azzerata", n=n), ephemeral=True)

    @comando_di_gruppo("admin-giochi", nome="togli-utente", descrizione="Toglie dalla tela tutti i pixel messi da una persona.", sottogruppo=SG_TELA_ADMIN)
    @app_commands.describe(utente="Di chi sono i pixel da togliere")
    @richiedi(Livello.ADMIN)
    async def togli_utente(self, interaction: discord.Interaction, utente: discord.User) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(await testo_per(interaction, "guild_only_command"), ephemeral=True)
            return
        n = await tela_repo.togli_utente(interaction.guild.id, utente.id)
        await interaction.response.send_message(await testo_per(interaction, "tela_utente_tolti", n=n, chi=utente.mention), ephemeral=True, allowed_mentions=NESSUNA_MENZIONE)

    @comando_di_gruppo("admin-giochi", nome="blocca", descrizione="Blocca una persona dalla tela di pixel.", sottogruppo=SG_TELA_ADMIN)
    @app_commands.describe(utente="Chi non potrà più colorare pixel")
    @richiedi(Livello.ADMIN)
    async def blocca(self, interaction: discord.Interaction, utente: discord.User) -> None:
        await self._blocco(interaction, utente, True)

    @comando_di_gruppo("admin-giochi", nome="sblocca", descrizione="Toglie il blocco dalla tela di pixel a una persona.", sottogruppo=SG_TELA_ADMIN)
    @app_commands.describe(utente="Chi può tornare a colorare pixel")
    @richiedi(Livello.ADMIN)
    async def sblocca(self, interaction: discord.Interaction, utente: discord.User) -> None:
        await self._blocco(interaction, utente, False)

    async def _blocco(self, interaction: discord.Interaction, utente: discord.User, bloccato: bool) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(await testo_per(interaction, "guild_only_command"), ephemeral=True)
            return
        cambiato = await tela_repo.imposta_blocco(interaction.guild.id, utente.id, bloccato)
        chiave = ("tela_blocca_ok" if cambiato else "tela_blocca_gia") if bloccato else ("tela_sblocca_ok" if cambiato else "tela_sblocca_gia")
        await interaction.response.send_message(await testo_per(interaction, chiave, chi=utente.mention), ephemeral=True, allowed_mentions=NESSUNA_MENZIONE)

    @comando_di_gruppo("admin-giochi", nome="impostazioni", descrizione="Pausa, costo per saltarla e pagina pubblica della tela.", sottogruppo=SG_TELA_ADMIN)
    @app_commands.describe(pausa="Secondi tra un pixel e l'altro (30-3600)", costo_minuto="Monete per ogni minuto di pausa saltato (0 = non si può)",
                           pubblica="Accende o spegne la pagina web pubblica in sola lettura")
    @richiedi(Livello.ADMIN)
    async def impostazioni(self, interaction: discord.Interaction, pausa: app_commands.Range[int, tl.PAUSA_MIN, tl.PAUSA_MAX] | None = None,
                           costo_minuto: app_commands.Range[int, 0, tl.COSTO_MINUTO_MAX] | None = None, pubblica: bool | None = None) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(await testo_per(interaction, "guild_only_command"), ephemeral=True)
            return
        imp = await tela_repo.imposta(interaction.guild.id, pausa_secondi=pausa, costo_minuto=costo_minuto, pubblica=pubblica)
        si, no = await testo_per(interaction, "fun_servizi_acceso"), await testo_per(interaction, "fun_servizi_spento")
        testo = await testo_per(interaction, "tela_imp", pausa=imp.pausa_secondi, costo=imp.costo_minuto, pubblica=si if imp.pubblica else no)
        if imp.pubblica and (link := indirizzo_pubblico(interaction.guild.id)):
            testo += "\n" + await testo_per(interaction, "tela_link", link=link)
        await interaction.response.send_message(testo, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(TelaCog(bot))
