"""
cogs/leveling/contenuti.py
==========================
Comandi di guadagno creati dal server (/admin-economia-negozio guadagno crea|elimina, /monete rischio guadagna), righe del
profilo scelte dall'utente (/level righe) e oggetti dal fondo premi (/admin-economia-negozio fondo dai).
Funzioni coperte: ECO-039, ECO-152, ECO-120
Dipende da: core/repositories/contenuti_repo.py
"""

from __future__ import annotations

import random

import discord
from discord import app_commands
from discord.ext import commands

from cogs.leveling.leveling import _comando_rifiutato
from cogs.leveling.rischio import _SG_RISCHIO
from core.command_groups import CogConGruppi, comando_di_gruppo, togli_comandi_del_cog, SOTTOGRUPPI
from core.i18n import testo_per
from core.repositories.animali_repo import animali_repo
from core.repositories.contenuti_repo import MAX_COMANDI_GUADAGNO, RIGHE_PROFILO, contenuti_repo
from core.repositories.leveling_settings_repo import leveling_settings_repo
from core.repositories.mercato_repo import mercato_repo
from core.repositories.rischio_repo import rischio_repo
from core.repositories.sociale_repo import sociale_repo

RNG = random.SystemRandom()
NESSUNA_MENZIONE = discord.AllowedMentions.none()
SG_GUADAGNO = ("guadagno", "Comandi di guadagno del server")
SG_FONDO = ("fondo", "Fondo premi del server")
NOME = app_commands.Range[str, 1, 20]


def leggi_righe(testo: str) -> list[str] | None:
    """«monete, banca» -> ['monete', 'banca'] (senza doppioni, solo righe note). None se non valido."""
    righe = [p.strip().lower() for p in testo.split(",") if p.strip()]
    if not righe or len(set(righe)) != len(righe) or any(r not in RIGHE_PROFILO for r in righe):
        return None
    return righe


class ContenutiCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    def cog_unload(self) -> None:
        togli_comandi_del_cog(self)

    # ------------------------------------------------------------------ ECO-039
    @comando_di_gruppo("admin-economia-negozio", nome="crea", descrizione="Crea un comando di guadagno: chi lo usa riceve monete, con una pausa.", sottogruppo=SOTTOGRUPPI["admin-economia-negozio guadagno"])
    @app_commands.describe(nome="Nome (lettere minuscole, numeri e trattini)", minimo="Monete minime", massimo="Monete massime (fino a 10000)",
                           pausa_minuti="Minuti di pausa per persona (1-10080)", testo="Frase mostrata; {monete} diventa l'importo")
    async def guadagno_crea(
        self, interaction: discord.Interaction, nome: NOME, minimo: app_commands.Range[int, 0, 10_000], massimo: app_commands.Range[int, 1, 10_000],
        pausa_minuti: app_commands.Range[int, 1, 10_080], testo: app_commands.Range[str, 1, 200],
    ) -> None:
        if await _comando_rifiutato(interaction):
            return
        nome = nome.lower()
        if minimo > massimo or not all(c.isascii() and (c.isalnum() or c == "-") for c in nome):
            await interaction.response.send_message(await testo_per(interaction, "con_dati_no"), ephemeral=True)
            return
        esito = await contenuti_repo.crea_comando(
            interaction.guild.id, nome, minimo, massimo, pausa_minuti * 60, discord.utils.escape_mentions(testo), interaction.user.id
        )
        await interaction.response.send_message(await testo_per(interaction, f"con_crea_{esito}", massimo=MAX_COMANDI_GUADAGNO), ephemeral=True)

    @comando_di_gruppo("admin-economia-negozio", nome="elimina", descrizione="Elimina un comando di guadagno del server.", sottogruppo=SOTTOGRUPPI["admin-economia-negozio guadagno"])
    @app_commands.describe(nome="Nome del comando")
    async def guadagno_elimina(self, interaction: discord.Interaction, nome: NOME) -> None:
        if await _comando_rifiutato(interaction):
            return
        ok = await contenuti_repo.togli_comando(interaction.guild.id, nome.lower())
        await interaction.response.send_message(await testo_per(interaction, "con_tolto" if ok else "con_non_esiste"), ephemeral=True)

    @comando_di_gruppo("monete", nome="guadagna", descrizione="Usa un comando di guadagno creato dal server (senza nome: l'elenco).", sottogruppo=_SG_RISCHIO)
    @app_commands.describe(nome="Nome del comando")
    async def guadagna(self, interaction: discord.Interaction, nome: NOME | None = None) -> None:
        if await _comando_rifiutato(interaction):
            return
        g, u = interaction.guild.id, interaction.user.id
        if nome is None:
            elenco = await contenuti_repo.comandi(g)
            testo = "\n".join(f"`{c.nome}` {c.minimo}-{c.massimo} / {c.pausa_s // 60} min" for c in elenco) or await testo_per(interaction, "con_nessuno")
            await interaction.response.send_message(testo[:1900], ephemeral=True)
            return
        c = await contenuti_repo.comando(g, nome.lower())
        if c is None:
            await interaction.response.send_message(await testo_per(interaction, "con_non_esiste"), ephemeral=True)
            return
        importo = RNG.randint(c.minimo, c.massimo)
        saldo = await rischio_repo.guadagna(g, u, f"cmd:{c.nome}", c.pausa_s, importo)
        if saldo is None:
            resto = await rischio_repo.pausa_rimasta(g, u, f"cmd:{c.nome}", c.pausa_s)
            await interaction.response.send_message(await testo_per(interaction, "con_pausa", minuti=max(1, resto // 60)), ephemeral=True)
            return
        moneta = (await leveling_settings_repo.get_config(g)).impostazioni.currency_name
        await interaction.response.send_message(
            (c.testo.replace("{monete}", f"{importo} {moneta}") + f"\n💰 {saldo} {moneta}")[:1900], allowed_mentions=NESSUNA_MENZIONE
        )

    # ------------------------------------------------------------------ ECO-152
    @comando_di_gruppo("level", nome="righe", descrizione="Scegli quali righe mostrare nel tuo riepilogo e in che ordine.")
    @app_commands.describe(scelta=f"Righe, con la virgola: {','.join(RIGHE_PROFILO)}")
    async def righe(self, interaction: discord.Interaction, scelta: app_commands.Range[str, 1, 100] | None = None) -> None:
        if await _comando_rifiutato(interaction):
            return
        g, u = interaction.guild.id, interaction.user.id
        if scelta is not None:
            nuove = leggi_righe(scelta)
            if nuove is None:
                await interaction.response.send_message(await testo_per(interaction, "con_righe_no", elenco=", ".join(RIGHE_PROFILO)), ephemeral=True)
                return
            await contenuti_repo.imposta_righe(g, u, nuove)
        moneta = (await leveling_settings_repo.get_config(g)).impostazioni.currency_name
        banca = await rischio_repo.banca(g, u)
        valori = {
            "monete": banca.contanti, "banca": banca.banca, "animali": len(await animali_repo.elenco(g, u)),
            "partner": await sociale_repo.coniuge(g, u), "prestigio": await sociale_repo.livello_prestigio(g, u), "amici": len(await sociale_repo.amici_di(g, u)),
        }
        righe = []
        for r in await contenuti_repo.righe(g, u):
            v = valori[r]
            righe.append(f"**{await testo_per(interaction, f'con_riga_{r}')}**: " + (f"<@{v}>" if r == "partner" and v else ("-" if r == "partner" else (f"{v} {moneta}" if r in ("monete", "banca") else str(v)))))
        await interaction.response.send_message("\n".join(righe), ephemeral=True, allowed_mentions=NESSUNA_MENZIONE)

    # ------------------------------------------------------------------ ECO-120
    @comando_di_gruppo("admin-economia-negozio", nome="dai", descrizione="Dai a un membro un oggetto donato al fondo premi.", sottogruppo=SOTTOGRUPPI["admin-economia-negozio fondo"])
    @app_commands.describe(membro="Chi lo riceve", oggetto="ID dell'oggetto (vedi /monete mercato fondo)")
    async def fondo_dai(self, interaction: discord.Interaction, membro: discord.Member, oggetto: app_commands.Range[int, 1, 2_147_483_647]) -> None:
        if await _comando_rifiutato(interaction):
            return
        if membro.bot:
            await interaction.response.send_message(await testo_per(interaction, "con_dati_no"), ephemeral=True)
            return
        ok = await mercato_repo.dai_dal_fondo(interaction.guild.id, membro.id, oggetto)
        await interaction.response.send_message(await testo_per(interaction, "con_fondo_dato" if ok else "con_fondo_vuoto"), ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ContenutiCog(bot))
