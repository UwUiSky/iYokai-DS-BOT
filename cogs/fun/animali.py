"""
cogs/fun/animali.py
===================
Animali virtuali e pesca: /fun animali compra, lista, cura, posto, attivita; /fun pesca lancia, vendi, guida, classifica.
Gli animali ben tenuti danno un piccolo bonus a lavoro e premio periodico (applicato in cogs/leveling/leveling.py).
Funzioni coperte: ECO-122, ECO-123, ECO-124, ECO-130, ECO-131, ECO-132, ECO-133, ECO-134, ECO-138
Dipende da: core/animali_logic.py, core/repositories/animali_repo.py
"""

from __future__ import annotations

import random
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from cogs.leveling.leveling import _comando_rifiutato, _format_seconds
from core.animali_logic import (
    ATTIVITA, LUOGHI_PESCA, MAX_NOME, PAUSA_ATTIVITA, PAUSA_PESCA, PESCI, SPECIE, livello, nome_valido, pesca,
    premio_attivita, salute, valore_pesci, valore_stato,
)
from core.command_groups import CogConGruppi, comando_di_gruppo, togli_comandi_del_cog
from core.i18n import testo_per
from core.animali_avanzati_logic import bonus_vendita, capienza, pausa_pesca, pesca_con
from core.repositories.animali_repo import animali_repo
from core.repositories.pesca_repo import pesca_repo
from core.repositories.leveling_settings_repo import leveling_settings_repo
from core.repositories.rischio_repo import rischio_repo

RNG = random.SystemRandom()
NESSUNA_MENZIONE = discord.AllowedMentions.none()
SG_ANIMALI = ("animali", "Animali da accudire")
SG_PESCA = ("pesca", "Pesca: lancia, vendi e completa la guida")
_SCELTE_SPECIE = [app_commands.Choice(name=f"{n.capitalize()} ({v[0]})", value=n) for n, v in SPECIE.items()]
_SCELTE_CURA = [app_commands.Choice(name="Dai da mangiare (5 monete)", value="fame"), app_commands.Choice(name="Pulisci", value="igiene"),
                app_commands.Choice(name="Gioca", value="gioco")]
_SCELTE_ATTIVITA = [app_commands.Choice(name=n.capitalize(), value=n) for n in ATTIVITA]
_SCELTE_LUOGO = [app_commands.Choice(name=n.capitalize(), value=n) for n in LUOGHI_PESCA]
IdAnimale = app_commands.Range[int, 1, 2**53 - 1]


class AnimaliCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    def cog_unload(self) -> None:
        togli_comandi_del_cog(self)

    async def _moneta(self, guild_id: int) -> str:
        return (await leveling_settings_repo.get_config(guild_id)).impostazioni.currency_name

    # ---------------------------------------------------------------- animali
    @comando_di_gruppo("fun", nome="compra", descrizione="Compra un animale da accudire.", sottogruppo=SG_ANIMALI)
    @app_commands.describe(specie="Che animale", nome=f"Come lo chiami (massimo {MAX_NOME} caratteri)")
    @app_commands.choices(specie=_SCELTE_SPECIE)
    async def compra(self, interaction: discord.Interaction, specie: app_commands.Choice[str], nome: app_commands.Range[str, 1, MAX_NOME]) -> None:
        if await _comando_rifiutato(interaction):
            return
        try:
            nome = nome_valido(nome)
        except ValueError as e:
            await interaction.response.send_message(f"❌ {e}", ephemeral=True)
            return
        esito = await animali_repo.compra(interaction.guild.id, interaction.user.id, specie.value, nome)
        await interaction.response.send_message(
            await testo_per(interaction, f"ani_compra_{esito}", specie=specie.value, nome=nome, prezzo=SPECIE[specie.value][0], moneta=await self._moneta(interaction.guild.id)),
            ephemeral=esito != "ok", allowed_mentions=NESSUNA_MENZIONE,
        )

    @comando_di_gruppo("fun", nome="lista", descrizione="I tuoi animali: fame, pulizia, gioco e livello.", sottogruppo=SG_ANIMALI)
    async def lista(self, interaction: discord.Interaction) -> None:
        if await _comando_rifiutato(interaction):
            return
        adesso = datetime.now(timezone.utc)
        righe = await animali_repo.elenco(interaction.guild.id, interaction.user.id)
        if not righe:
            await interaction.response.send_message(await testo_per(interaction, "ani_nessuno"), ephemeral=True)
            return
        testo = "\n".join(
            f"`{r['id']}` **{discord.utils.escape_markdown(r['nome'])}** ({r['specie']}) · 🍖 {valore_stato(r['fame_at'], adesso, 'fame')} · 🛁 {valore_stato(r['igiene_at'], adesso, 'igiene')} "
            f"· 🎾 {valore_stato(r['gioco_at'], adesso, 'gioco')} · livello {livello(r['xp'])}"
            for r in righe
        )
        await interaction.response.send_message(testo[:3900], ephemeral=True, allowed_mentions=NESSUNA_MENZIONE)

    @comando_di_gruppo("fun", nome="cura", descrizione="Dai da mangiare, pulisci o gioca con un animale (una volta all'ora per tipo).", sottogruppo=SG_ANIMALI)
    @app_commands.describe(animale="ID dell'animale (vedi /fun animali lista)", cosa="Cosa fai")
    @app_commands.choices(cosa=_SCELTE_CURA)
    async def cura(self, interaction: discord.Interaction, animale: IdAnimale, cosa: app_commands.Choice[str]) -> None:
        if await _comando_rifiutato(interaction):
            return
        esito = await animali_repo.cura(interaction.guild.id, interaction.user.id, animale, cosa.value)
        await interaction.response.send_message(await testo_per(interaction, f"ani_cura_{esito}"), ephemeral=esito != "ok")

    @comando_di_gruppo("fun", nome="posto", descrizione="Compra un posto in più per un altro animale (massimo 2 in più).", sottogruppo=SG_ANIMALI)
    async def posto(self, interaction: discord.Interaction) -> None:
        if await _comando_rifiutato(interaction):
            return
        esito, costo = await animali_repo.compra_posto(interaction.guild.id, interaction.user.id)
        await interaction.response.send_message(
            await testo_per(interaction, f"ani_posto_{esito}", costo=costo, moneta=await self._moneta(interaction.guild.id)), ephemeral=esito != "ok"
        )

    @comando_di_gruppo("fun", nome="attivita", descrizione="Un'attività con un tuo animale in salute: ti porta qualche moneta (ogni 2 ore).", sottogruppo=SG_ANIMALI)
    @app_commands.describe(animale="ID dell'animale", tipo="Che attività")
    @app_commands.choices(tipo=_SCELTE_ATTIVITA)
    async def attivita(self, interaction: discord.Interaction, animale: IdAnimale, tipo: app_commands.Choice[str]) -> None:
        if await _comando_rifiutato(interaction):
            return
        g, u = interaction.guild.id, interaction.user.id
        adesso = datetime.now(timezone.utc)
        mio = next((r for r in await animali_repo.elenco(g, u) if r["id"] == animale), None)
        if mio is None:
            await interaction.response.send_message(await testo_per(interaction, "ani_cura_non_tuo"), ephemeral=True)
            return
        sano = salute(mio["fame_at"], mio["igiene_at"], mio["gioco_at"], adesso) >= 30
        monete = premio_attivita(RNG, livello(mio["xp"]))
        saldo = await animali_repo.attivita(g, u, animale, monete, sano)
        if saldo is None:
            await interaction.response.send_message(await testo_per(interaction, "ani_attivita_no", tempo=_format_seconds(PAUSA_ATTIVITA)), ephemeral=True)
            return
        await interaction.response.send_message(
            await testo_per(interaction, "ani_attivita_ok", nome=mio["nome"][:20], tipo=tipo.value, monete=monete, moneta=await self._moneta(g), pubblica=True),
            allowed_mentions=NESSUNA_MENZIONE,
        )

    # ---------------------------------------------------------------- pesca
    @comando_di_gruppo("fun", nome="lancia", descrizione="Getta la lenza in un luogo (ogni 15 minuti).", sottogruppo=SG_PESCA)
    @app_commands.describe(luogo="Dove peschi")
    @app_commands.choices(luogo=_SCELTE_LUOGO)
    async def lancia(self, interaction: discord.Interaction, luogo: app_commands.Choice[str]) -> None:
        if await _comando_rifiutato(interaction):
            return
        g, u = interaction.guild.id, interaction.user.id
        profilo = await pesca_repo.profilo(g, u)  # ECO-135/137: abilità, esche e canna cambiano pausa, deposito e probabilità
        pausa, cap = pausa_pesca(set(profilo.abilita), profilo.canna), capienza(set(profilo.abilita))
        specie = pesca_con(RNG, luogo.value, set(profilo.abilita), profilo.esche > 0)
        esito = await animali_repo.pesca(g, u, datetime.now(timezone.utc).date(), specie, pausa, capienza=cap, usa_esca=profilo.esche > 0)
        if esito is None:
            resto = await rischio_repo.pausa_rimasta(g, u, "pesca", pausa)
            chiave = "rsk_pausa" if resto > 0 else "pes_pieno"
            await interaction.response.send_message(await testo_per(interaction, chiave, tempo=_format_seconds(max(1, resto))), ephemeral=True)
            return
        if esito is False:
            await interaction.response.send_message(await testo_per(interaction, "pes_niente", luogo=luogo.value, pubblica=True))
            return
        await interaction.response.send_message(await testo_per(interaction, "pes_preso", pesce=specie, emoji=PESCI[specie][1], luogo=luogo.value, pubblica=True))

    @comando_di_gruppo("fun", nome="vendi", descrizione="Vendi tutti i pesci del deposito.", sottogruppo=SG_PESCA)
    async def vendi(self, interaction: discord.Interaction) -> None:
        if await _comando_rifiutato(interaction):
            return
        profilo = await pesca_repo.profilo(interaction.guild.id, interaction.user.id)
        n, monete = await animali_repo.vendi_pesci(interaction.guild.id, interaction.user.id, bonus_vendita(set(profilo.abilita)))
        if n == 0:
            await interaction.response.send_message(await testo_per(interaction, "pes_vuoto"), ephemeral=True)
            return
        await interaction.response.send_message(
            await testo_per(interaction, "pes_venduti", n=n, monete=monete, moneta=await self._moneta(interaction.guild.id)), ephemeral=True
        )

    @comando_di_gruppo("fun", nome="guida", descrizione="Il tuo deposito di pesci e le specie che hai già trovato.", sottogruppo=SG_PESCA)
    async def guida(self, interaction: discord.Interaction) -> None:
        if await _comando_rifiutato(interaction):
            return
        g, u = interaction.guild.id, interaction.user.id
        deposito, visti = await animali_repo.deposito(g, u), await animali_repo.visti(g, u)
        righe = [f"{PESCI[s][1]} {s} ({PESCI[s][0]}): " + (f"**{deposito.get(s, 0)}** nel deposito" if s in visti else "???") for s in PESCI]
        righe.append(await testo_per(interaction, "pes_guida", visti=len(visti), tutti=len(PESCI), valore=valore_pesci(deposito)))
        await interaction.response.send_message("\n".join(righe), ephemeral=True)

    @comando_di_gruppo("fun", nome="classifica", descrizione="I migliori pescatori di oggi.", sottogruppo=SG_PESCA)
    async def classifica_pesca(self, interaction: discord.Interaction) -> None:
        if await _comando_rifiutato(interaction):
            return
        righe = await animali_repo.classifica_giorno(interaction.guild.id, datetime.now(timezone.utc).date())
        if not righe:
            await interaction.response.send_message(await testo_per(interaction, "pes_nessuno"), ephemeral=True)
            return
        await interaction.response.send_message("\n".join(f"{n}. <@{r['user_id']}> — {r['punti']}" for n, r in enumerate(righe, 1)), allowed_mentions=NESSUNA_MENZIONE)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AnimaliCog(bot))
