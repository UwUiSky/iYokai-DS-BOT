"""
cogs/leveling/guadagno.py
=========================
/admin-livelli guadagno (formula, messaggi, comandi, prefissi, canali): come si guadagna XP.
Formula dei livelli, XP a parola e bonus impegno, XP dei comandi slash, prefissi di altri bot
da ignorare, elenco dei canali come lista bianca.
Funzioni coperte: SPEC §15 (LIV-004, 006, 007, 017, 018, 021; catalogo #124)
Dipende da: core/leveling_logic.py, core/repositories/leveling_settings_repo.py
"""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from cogs.leveling.azzeramenti import _bloccato, _puo_gestire
from cogs.leveling.leveling import _comando_rifiutato
from core.command_groups import SOTTOGRUPPI, CogConGruppi, comando_di_gruppo, togli_comandi_del_cog
from core.i18n import testo_per
from core.leveling_logic import MAX_LUNGHEZZA_PREFISSO, MAX_PREFISSI, MAX_REAZIONI_AL_GIORNO
from core.repositories.leveling_settings_repo import leveling_settings_repo

logger = logging.getLogger("iyokai.leveling.guadagno")

_SG = SOTTOGRUPPI["admin-livelli guadagno"]
_NO_MENZIONI = discord.AllowedMentions.none()

_SCELTE_FORMULA = [
    app_commands.Choice(name="Classica (di base)", value="classica"),
    app_commands.Choice(name="Lineare", value="lineare"),
    app_commands.Choice(name="Esponenziale", value="esponenziale"),
    app_commands.Choice(name="Costante", value="costante"),
]
_SCELTE_MODO_XP = [
    app_commands.Choice(name="Fisso per messaggio (di base)", value="fisso"),
    app_commands.Choice(name="A parola", value="parola"),
]
_SCELTE_AZIONE_PREFISSI = [
    app_commands.Choice(name="Aggiungi", value="aggiungi"),
    app_commands.Choice(name="Togli", value="togli"),
    app_commands.Choice(name="Elenco", value="elenco"),
    app_commands.Choice(name="Togli tutti", value="azzera"),
]
_SCELTE_MODO_CANALI = [
    app_commands.Choice(name="Tutti tranne quelli esclusi (di base)", value="tutti"),
    app_commands.Choice(name="Solo i canali dell'elenco", value="solo_questi"),
]


async def _rispondi(interaction: discord.Interaction, chiave: str, **valori) -> None:
    await interaction.response.send_message(
        await testo_per(interaction, chiave, **valori), ephemeral=True, allowed_mentions=_NO_MENZIONI
    )


class GuadagnoCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    def cog_unload(self) -> None:
        togli_comandi_del_cog(self)

    # ---------------------------------------------------------------- LIV-004
    @comando_di_gruppo(
        "admin-livelli",
        nome="formula",
        descrizione="Sceglie la curva dei livelli e ricalcola i livelli di tutti.",
        sottogruppo=_SG,
    )
    @app_commands.describe(formula="Classica, lineare, esponenziale o costante")
    @app_commands.choices(formula=_SCELTE_FORMULA)
    async def guadagno_formula(self, interaction: discord.Interaction, formula: app_commands.Choice[str]) -> None:
        if await _comando_rifiutato(interaction):
            return
        # Cambia il livello di tutto il server: lo stesso blocco degli azzeramenti.
        if not await _puo_gestire(interaction) or await _bloccato(interaction, "blocca_azzeramento"):
            return
        await interaction.response.defer(ephemeral=True)
        cambiate = await leveling_settings_repo.cambia_formula(interaction.guild.id, formula.value)
        logger.info(
            "Formula dei livelli cambiata: server %s, staff %s, %s (%s livelli).",
            interaction.guild.id, interaction.user.id, formula.value, cambiate,
        )
        await interaction.followup.send(
            await testo_per(interaction, "gua_formula_ok", formula=formula.name, n=cambiate),
            ephemeral=True, allowed_mentions=_NO_MENZIONI,
        )

    # ---------------------------------------------------------------- LIV-006 e 007
    @comando_di_gruppo(
        "admin-livelli",
        nome="messaggi",
        descrizione="XP per messaggio: fisso o a parola, più il bonus per messaggi lunghi o con immagini.",
        sottogruppo=_SG,
    )
    @app_commands.describe(
        modo="Fisso per messaggio oppure a parola",
        xp_parola="XP per ogni parola da 3 lettere in su (1-10)",
        parole_max="Parole contate al massimo per messaggio (1-100)",
        bonus="XP in più per un messaggio lungo o con immagine (0-50, 0 = spento)",
        caratteri="Da quanti caratteri un messaggio è «lungo» (20-2000)",
    )
    @app_commands.choices(modo=_SCELTE_MODO_XP)
    async def guadagno_messaggi(
        self,
        interaction: discord.Interaction,
        modo: app_commands.Choice[str] | None = None,
        xp_parola: app_commands.Range[int, 1, 10] | None = None,
        parole_max: app_commands.Range[int, 1, 100] | None = None,
        bonus: app_commands.Range[int, 0, 50] | None = None,
        caratteri: app_commands.Range[int, 20, 2000] | None = None,
    ) -> None:
        if await _comando_rifiutato(interaction):
            return
        if not await _puo_gestire(interaction):
            return
        campi = {}
        if modo is not None:
            campi["xp_modo"] = modo.value
        for nome, valore in (
            ("xp_per_parola", xp_parola), ("parole_max", parole_max),
            ("bonus_impegno", bonus), ("impegno_caratteri", caratteri),
        ):
            if valore is not None:
                campi[nome] = valore
        if campi:
            await leveling_settings_repo.set_options(interaction.guild.id, **campi)
            logger.info("Guadagno XP dei messaggi cambiato: server %s, staff %s, %s.", interaction.guild.id, interaction.user.id, campi)
        i = (await leveling_settings_repo.get_config(interaction.guild.id, fresco=True)).impostazioni
        await _rispondi(
            interaction, "gua_messaggi_ok",
            modo=await testo_per(interaction, f"gua_modo_{i.xp_modo}"),
            testo=i.text_xp, parola=i.xp_per_parola, massimo=i.parole_max,
            bonus=i.bonus_impegno, caratteri=i.impegno_caratteri,
        )

    # ---------------------------------------------------------------- LIV-017
    @comando_di_gruppo(
        "admin-livelli",
        nome="comandi",
        descrizione="Accende o spegne l'XP per l'uso dei comandi slash (di base spento).",
        sottogruppo=_SG,
    )
    @app_commands.describe(attivo="Sì = un comando riuscito dà XP (con la stessa pausa dei messaggi)")
    async def guadagno_comandi(self, interaction: discord.Interaction, attivo: bool) -> None:
        if await _comando_rifiutato(interaction):
            return
        if not await _puo_gestire(interaction):
            return
        await leveling_settings_repo.set_options(interaction.guild.id, xp_comandi=attivo)
        await _rispondi(interaction, "gua_comandi_acceso" if attivo else "gua_comandi_spento")

    # ---------------------------------------------------------------- LIV-018
    @comando_di_gruppo(
        "admin-livelli",
        nome="prefissi",
        descrizione="Prefissi di altri bot: i messaggi che iniziano così non danno XP.",
        sottogruppo=_SG,
    )
    @app_commands.describe(
        azione="Cosa fare con l'elenco (al massimo 10 prefissi)",
        prefisso="Il prefisso, per esempio ! oppure ?",
    )
    @app_commands.choices(azione=_SCELTE_AZIONE_PREFISSI)
    async def guadagno_prefissi(
        self,
        interaction: discord.Interaction,
        azione: app_commands.Choice[str],
        prefisso: app_commands.Range[str, 1, MAX_LUNGHEZZA_PREFISSO] | None = None,
    ) -> None:
        if await _comando_rifiutato(interaction):
            return
        if not await _puo_gestire(interaction):
            return
        guild_id = interaction.guild.id
        if azione.value in ("aggiungi", "togli") and prefisso is None:
            await _rispondi(interaction, "gua_serve_prefisso")
            return
        if azione.value == "aggiungi":
            esito = await leveling_settings_repo.aggiungi_prefisso(guild_id, prefisso)
            await _rispondi(interaction, f"gua_prefisso_{esito}", max=MAX_PREFISSI)
            return
        if azione.value == "togli":
            await leveling_settings_repo.togli_prefisso(guild_id, prefisso)
        elif azione.value == "azzera":
            await leveling_settings_repo.togli_prefisso(guild_id, None)
        elenco = (await leveling_settings_repo.get_config(guild_id, fresco=True)).impostazioni.prefissi_ignorati
        if not elenco:
            await _rispondi(interaction, "gua_prefissi_nessuno")
            return
        # Il testo è degli utenti: in blocco di codice, senza accenti gravi dentro.
        righe = " ".join(f"`{p.replace('`', '')}`" for p in elenco)
        await _rispondi(interaction, "gua_prefissi_elenco", elenco=righe, n=len(elenco))

    # ---------------------------------------------------------------- LIV-021
    @comando_di_gruppo(
        "admin-livelli",
        nome="canali",
        descrizione="Dà XP in tutti i canali tranne gli esclusi, oppure solo in quelli dell'elenco.",
        sottogruppo=_SG,
    )
    @app_commands.describe(modo="L'elenco è di canali esclusi (di base) oppure di soli canali che danno XP")
    @app_commands.choices(modo=_SCELTE_MODO_CANALI)
    async def guadagno_canali(self, interaction: discord.Interaction, modo: app_commands.Choice[str]) -> None:
        if await _comando_rifiutato(interaction):
            return
        if not await _puo_gestire(interaction):
            return
        await leveling_settings_repo.set_options(interaction.guild.id, canali_modo=modo.value)
        config = await leveling_settings_repo.get_config(interaction.guild.id, fresco=True)
        if modo.value == "solo_questi" and not config.canali_esclusi:
            await _rispondi(interaction, "gua_canali_solo_vuoto")
        else:
            await _rispondi(interaction, f"gua_canali_{modo.value}", n=len(config.canali_esclusi))

    # ---------------------------------------------------------------- LIV-014, 015, 016
    @comando_di_gruppo(
        "admin-livelli",
        nome="contesti",
        descrizione="Se thread, post dei forum e chat dei canali vocali danno XP.",
        sottogruppo=_SG,
    )
    @app_commands.describe(
        thread="Sì = i messaggi nei thread danno XP (valgono le regole del canale padre)",
        forum="Sì = i messaggi nei post dei forum danno XP",
        chat_vocale="Sì = i messaggi scritti nella chat dei canali vocali danno XP",
    )
    async def guadagno_contesti(
        self,
        interaction: discord.Interaction,
        thread: bool | None = None,
        forum: bool | None = None,
        chat_vocale: bool | None = None,
    ) -> None:
        if await _comando_rifiutato(interaction):
            return
        if not await _puo_gestire(interaction):
            return
        campi = {
            n: v for n, v in (("xp_thread", thread), ("xp_forum", forum), ("xp_chat_vocale", chat_vocale))
            if v is not None
        }
        if campi:
            await leveling_settings_repo.set_options(interaction.guild.id, **campi)
        i = (await leveling_settings_repo.get_config(interaction.guild.id, fresco=True)).impostazioni
        si, no = await testo_per(interaction, "azz_si"), await testo_per(interaction, "azz_no")
        await _rispondi(
            interaction, "gua_contesti_ok",
            thread=si if i.xp_thread else no, forum=si if i.xp_forum else no,
            chat=si if i.xp_chat_vocale else no,
        )

    # ---------------------------------------------------------------- LIV-011, 012
    @comando_di_gruppo(
        "admin-livelli",
        nome="vocale",
        descrizione="XP in vocale: persone minime nel canale e controllo anti-farm.",
        sottogruppo=_SG,
    )
    @app_commands.describe(
        persone="Persone nel canale (te compreso) perché si prenda XP: da 1 a 10",
        anti_farm="Sì = niente XP a chi è assordato e conta solo chi non è muto (di base sì)",
        max_minuti="Minuti al giorno in vocale che danno XP e monete (30-1440; di base 360)",  # ECO-161
    )
    async def guadagno_vocale(
        self,
        interaction: discord.Interaction,
        persone: app_commands.Range[int, 1, 10] | None = None,
        anti_farm: bool | None = None,
        max_minuti: app_commands.Range[int, 30, 1440] | None = None,
    ) -> None:
        if await _comando_rifiutato(interaction):
            return
        if not await _puo_gestire(interaction):
            return
        campi = {n: v for n, v in (("voce_min_persone", persone), ("anti_farm", anti_farm), ("voce_max_minuti", max_minuti)) if v is not None}
        if campi:
            await leveling_settings_repo.set_options(interaction.guild.id, **campi)
            logger.info("XP vocale cambiato: server %s, staff %s, %s.", interaction.guild.id, interaction.user.id, campi)
        i = (await leveling_settings_repo.get_config(interaction.guild.id, fresco=True)).impostazioni
        si, no = await testo_per(interaction, "azz_si"), await testo_per(interaction, "azz_no")
        await _rispondi(
            interaction, "gua_vocale_ok", persone=i.voce_min_persone, anti=si if i.anti_farm else no,
            xp=i.voice_xp_per_minute, monete=i.voice_coins_per_minute,
        )

    # ---------------------------------------------------------------- LIV-008, 009
    @comando_di_gruppo(
        "admin-livelli",
        nome="reazioni",
        descrizione="XP per le reazioni messe e ricevute (di base spento).",
        sottogruppo=_SG,
    )
    @app_commands.describe(
        messa="XP a chi mette una reazione (0-20, 0 = spento)",
        ricevuta="XP a chi riceve una reazione sul suo messaggio (0-20, 0 = spento)",
        attesa="Secondi tra due reazioni che danno XP, per persona (60-3600)",
    )
    async def guadagno_reazioni(
        self,
        interaction: discord.Interaction,
        messa: app_commands.Range[int, 0, 20] | None = None,
        ricevuta: app_commands.Range[int, 0, 20] | None = None,
        attesa: app_commands.Range[int, 60, 3600] | None = None,
    ) -> None:
        if await _comando_rifiutato(interaction):
            return
        if not await _puo_gestire(interaction):
            return
        campi = {
            n: v for n, v in (
                ("xp_reazione_messa", messa), ("xp_reazione_ricevuta", ricevuta), ("reazioni_attesa", attesa),
            ) if v is not None
        }
        if campi:
            await leveling_settings_repo.set_options(interaction.guild.id, **campi)
            logger.info("XP delle reazioni cambiato: server %s, staff %s, %s.", interaction.guild.id, interaction.user.id, campi)
        i = (await leveling_settings_repo.get_config(interaction.guild.id, fresco=True)).impostazioni
        await _rispondi(
            interaction, "gua_reazioni_ok", messa=i.xp_reazione_messa, ricevuta=i.xp_reazione_ricevuta,
            attesa=i.reazioni_attesa, tetto=MAX_REAZIONI_AL_GIORNO,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(GuadagnoCog(bot))
