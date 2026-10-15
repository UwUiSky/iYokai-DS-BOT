"""
cogs/leveling/profiles.py
=========================
Profilo personale (/level profilo, come immagine con l'eventuale sfondo
proprio di /level rank) e collezione di badge e sfondi comprati con le coin
(/level collezione).
Funzioni coperte: SPEC §23.16 (NF-40)
Dipende da: core/profile_logic.py, core/repositories/profile_repo.py, core/rank_card_image.py
"""

from __future__ import annotations

import io
import logging

import discord
from discord import app_commands
from discord.ext import commands

from cogs.leveling._pagine import taglia
from cogs.leveling.leveling import _comando_rifiutato
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.profile_logic import (
    CATALOGO,
    COLORE_DI_BASE,
    MAX_BIO,
    TIPO_BADGE,
    TIPO_SFONDO,
    oggetto,
    pulisci_bio,
    riga_oggetto,
)
from core.rank_card_image import TEMA_DI_BASE, DatiProfilo, render_profile_card
from core.repositories.leveling_repo import leveling_repo
from core.repositories.leveling_settings_repo import leveling_settings_repo
from core.repositories.profile_repo import EsitoAcquisto, profile_repo
from core.safe_image import run_image_task

logger = logging.getLogger("iyokai.profiles")

_SG_COLLEZIONE = ("collezione", "Collezione: badge e sfondi per il tuo profilo, da comprare con le coin.")

_SCELTE_OGGETTO = [
    app_commands.Choice(name=f"{o.emoji or '🎨'} {o.nome} ({o.prezzo} coin)", value=o.id)
    for o in CATALOGO
]
_SCELTE_TIPO = [
    app_commands.Choice(name="Badge", value=TIPO_BADGE),
    app_commands.Choice(name="Sfondo", value=TIPO_SFONDO),
]


class ProfilesCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ================================================================
    # /level profilo
    # ================================================================
    @comando_di_gruppo(
        "level",
        nome="profilo",
        descrizione="Mostra il profilo di un membro; con «presentazione» cambi il tuo.",
    )
    @app_commands.describe(
        membro="Il membro di cui vedere il profilo (facoltativo)",
        presentazione=f"La tua presentazione, al massimo {MAX_BIO} caratteri",
        cancella_presentazione="Togli la tua presentazione",
    )
    async def profilo(
        self,
        interaction: discord.Interaction,
        membro: discord.Member | None = None,
        presentazione: app_commands.Range[str, 1, MAX_BIO] | None = None,
        cancella_presentazione: bool | None = None,
    ) -> None:
        if await _comando_rifiutato(interaction):
            return
        guild = interaction.guild
        nota = ""
        if presentazione is not None or cancella_presentazione:
            if membro is not None and membro.id != interaction.user.id:
                await interaction.response.send_message(
                    "La presentazione si cambia solo sul proprio profilo.", ephemeral=True
                )
                return
            bio = None if cancella_presentazione else pulisci_bio(presentazione or "")
            await profile_repo.set_bio(guild.id, interaction.user.id, bio)
            nota = "✅ Presentazione salvata." if bio else "✅ Presentazione tolta."

        # Avatar, sfondo e disegno possono superare i 3 secondi.
        await interaction.response.defer()
        target = membro or interaction.user
        profilo = await profile_repo.get_profile(guild.id, target.id)
        totali = await leveling_repo.get_totals(guild.id, target.id)
        posizione = await leveling_repo.get_xp_position(guild.id, target.id)

        badge = oggetto(profilo.badge_id) if profilo.badge_id else None
        sfondo = oggetto(profilo.background_id) if profilo.background_id else None
        simbolo = f"{badge.emoji} " if badge is not None and profilo.badge_id in profilo.posseduti else ""
        colore = sfondo.colore if sfondo is not None and profilo.background_id in profilo.posseduti else COLORE_DI_BASE
        emoji = [o.emoji for o in CATALOGO if o.id in profilo.posseduti and o.emoji]

        try:
            png = await self._disegna(guild.id, target, profilo, totali, posizione, colore)
        except Exception:
            logger.exception("Profilo non disegnato per %s: mando l'embed.", target.id)
            png = None
        if png is not None:
            # I badge sono emoji: il font della card non le disegna, vanno nel testo.
            righe = [nota] if nota else []
            if emoji:
                righe.append(f"Badge: {simbolo}" + " ".join(e for e in emoji if f"{e} " != simbolo))
            await interaction.followup.send(
                "\n".join(righe)[:2000] or None,
                file=discord.File(io.BytesIO(png), filename="profilo.png"),
                allowed_mentions=discord.AllowedMentions.none(),
            )
            return

        embed = discord.Embed(
            title=taglia(f"{simbolo}{target.display_name}", 256),
            description=profilo.bio or "*Nessuna presentazione.*",
            color=discord.Color(colore),
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name="Livello", value=str(totali.level), inline=True)
        embed.add_field(name="XP", value=str(totali.xp_total), inline=True)
        embed.add_field(
            name="Posizione", value=f"#{posizione}" if posizione else "—", inline=True
        )
        embed.add_field(name="Coin", value=str(totali.coins_total), inline=True)
        embed.add_field(
            name="Collezione", value=f"{len(profilo.posseduti)}/{len(CATALOGO)}", inline=True
        )
        if emoji:
            embed.add_field(name="Badge", value=" ".join(emoji), inline=False)
        await interaction.followup.send(nota or None, embed=embed)

    async def _disegna(self, guild_id, target, profilo, totali, posizione, colore: int) -> bytes:
        """Il profilo come PNG: tema della rank card, colore dello sfondo comprato, immagine propria."""
        _, tema = await leveling_repo.get_rank_card_prefs(target.id)
        config = await leveling_settings_repo.get_config(guild_id)
        immagine = await leveling_repo.get_sfondo_card(target.id) if config.impostazioni.card_images else None
        try:
            avatar = await target.display_avatar.read()
        except Exception:  # anche errori di rete dopo il defer: il profilo esce senza avatar
            avatar = None
        dati = DatiProfilo(
            nome=target.display_name,
            presentazione=profilo.bio,
            livello=totali.level,
            xp_totale=totali.xp_total,
            posizione=posizione,
            coin=totali.coins_total,
            collezione=len(profilo.posseduti),
            collezione_totale=len(CATALOGO),
            colore=f"#{colore:06X}",
            tema=tema or TEMA_DI_BASE,
        )
        return await run_image_task(render_profile_card, dati, avatar, immagine)

    # ================================================================
    # /level collezione
    # ================================================================
    @comando_di_gruppo(
        "level",
        nome="negozio",
        descrizione="Mostra badge e sfondi in vendita e quelli che hai.",
        sottogruppo=_SG_COLLEZIONE,
    )
    async def collezione_negozio(self, interaction: discord.Interaction) -> None:
        if await _comando_rifiutato(interaction):
            return
        profilo = await profile_repo.get_profile(interaction.guild.id, interaction.user.id)
        righe = [riga_oggetto(o, o.id in profilo.posseduti) for o in CATALOGO]
        embed = discord.Embed(
            title="Collezione", description="\n".join(righe), color=discord.Color(COLORE_DI_BASE)
        )
        embed.set_footer(text="Si comprano con /level collezione compra. Le coin non si comprano con soldi veri.")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @comando_di_gruppo(
        "level",
        nome="compra",
        descrizione="Compra un badge o uno sfondo con le tue coin.",
        sottogruppo=_SG_COLLEZIONE,
    )
    @app_commands.describe(oggetto_scelto="Cosa comprare")
    @app_commands.rename(oggetto_scelto="oggetto")
    @app_commands.choices(oggetto_scelto=_SCELTE_OGGETTO)
    async def collezione_compra(
        self, interaction: discord.Interaction, oggetto_scelto: app_commands.Choice[str]
    ) -> None:
        if await _comando_rifiutato(interaction):
            return
        scelto = oggetto(oggetto_scelto.value)
        esito = await profile_repo.buy(interaction.guild.id, interaction.user.id, oggetto_scelto.value)
        if esito is EsitoAcquisto.COMPRATO:
            testo = (
                f"✅ Hai comprato **{scelto.nome}** per {scelto.prezzo} coin. "
                "Mettilo con `/level collezione equipaggia`."
            )
        elif esito is EsitoAcquisto.GIA_POSSEDUTO:
            testo = "Ce l'hai già."
        elif esito is EsitoAcquisto.SALDO_INSUFFICIENTE:
            totali = await leveling_repo.get_totals(interaction.guild.id, interaction.user.id)
            testo = f"Non hai abbastanza coin: ne hai **{totali.coins_total}**, ne servono **{scelto.prezzo}**."
        else:
            testo = "Questo oggetto non esiste."
        await interaction.response.send_message(testo, ephemeral=True)

    @comando_di_gruppo(
        "level",
        nome="equipaggia",
        descrizione="Metti un badge o uno sfondo sul tuo profilo (senza oggetto lo togli).",
        sottogruppo=_SG_COLLEZIONE,
    )
    @app_commands.describe(tipo="Badge o sfondo", oggetto_scelto="Cosa mettere (vuoto = toglilo)")
    @app_commands.rename(oggetto_scelto="oggetto")
    @app_commands.choices(tipo=_SCELTE_TIPO, oggetto_scelto=_SCELTE_OGGETTO)
    async def collezione_equipaggia(
        self,
        interaction: discord.Interaction,
        tipo: app_commands.Choice[str],
        oggetto_scelto: app_commands.Choice[str] | None = None,
    ) -> None:
        if await _comando_rifiutato(interaction):
            return
        id_scelto = oggetto_scelto.value if oggetto_scelto is not None else None
        riuscito = await profile_repo.equip(
            interaction.guild.id, interaction.user.id, tipo.value, id_scelto
        )
        if not riuscito:
            testo = "Non puoi: o non l'hai comprato, o non è un oggetto di quel tipo."
        elif id_scelto is None:
            testo = f"✅ {tipo.name} tolto."
        else:
            testo = f"✅ {oggetto(id_scelto).nome} messo sul tuo profilo."
        await interaction.response.send_message(testo, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ProfilesCog(bot))
