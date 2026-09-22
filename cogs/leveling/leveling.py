"""
cogs/leveling/leveling.py
============================
XP testuale (on_message) e vocale (task periodico ogni 60s), livelli,
economia di base (daily/work/pay/balance), classifiche mensili e
all-time. Modulo sempre gratuito, come da schema.

Message Content Intent: on_message NON richiede quell'intent per
scattare — il privilegio riguarda solo se message.content è
popolato o vuoto, non se l'evento MESSAGE_CREATE arriva. Qui non
leggiamo mai message.content (ci basta sapere CHE un messaggio è
stato inviato, non cosa dice), quindi questo modulo resta coerente
con la scelta di lasciare l'intent disattivato di default (vedi
main.py).

Il task periodico per l'XP vocale condivide l'evento
on_voice_state_update con cogs/voice_temp/voice_temp.py — è normale,
discord.py consegna lo stesso evento a tutti i cog che lo ascoltano
— ma qui usiamo un TASK PERIODICO (tasks.loop) invece di reagire
all'evento stesso, perché l'XP va accumulato minuto per minuto per
tutta la durata della permanenza in vocale, non solo al momento in
cui l'utente entra o esce.
"""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands, tasks

from core.database import db
from core.repositories.leveling_repo import leveling_repo
from core.leveling_logic import (
    DAILY_REWARD_COINS,
    WORK_REWARD_MAX,
    WORK_REWARD_MIN,
    can_claim_daily,
    can_claim_work,
    is_eligible_for_voice_xp,
    period_key,
    seconds_until_next_claim,
    xp_for_level,
)
from core.premium import PremiumModule, registry

logger = logging.getLogger("iyokai.leveling")

MODULE_LEVELING = "leveling"


def _format_seconds(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}s"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m"
    hours = minutes // 60
    remaining_minutes = minutes % 60
    return f"{hours}h {remaining_minutes}m"


class LevelingCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._voice_xp_tick.start()

    def cog_unload(self) -> None:
        self._voice_xp_tick.cancel()

    # ================================================================
    # XP testuale
    # ================================================================
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or message.guild is None:
            return

        if not await db.is_module_active_for_guild(message.guild.id, MODULE_LEVELING):
            return

        risultato = await leveling_repo.add_text_xp(message.guild.id, message.author.id)
        if risultato.granted and risultato.leveled_up:
            try:
                await message.channel.send(
                    f"🎉 {message.author.mention} è salito al livello **{risultato.new_level}**!"
                )
            except discord.HTTPException:
                pass

    # ================================================================
    # XP vocale — task periodico
    # ================================================================
    @tasks.loop(seconds=60)
    async def _voice_xp_tick(self) -> None:
        for guild in self.bot.guilds:
            try:
                if not await db.is_module_active_for_guild(guild.id, MODULE_LEVELING):
                    continue
                await self._process_guild_voice_xp(guild)
            except Exception:
                # Un errore in UN server non deve interrompere il
                # giro per tutti gli altri.
                logger.exception(
                    "Errore nel calcolo XP vocale per il server %s", guild.id
                )

    @_voice_xp_tick.before_loop
    async def _before_voice_xp_tick(self) -> None:
        await self.bot.wait_until_ready()

    async def _process_guild_voice_xp(self, guild: discord.Guild) -> None:
        afk_channel_id = guild.afk_channel.id if guild.afk_channel else None

        for channel in guild.voice_channels:
            members = [m for m in channel.members if not m.bot]
            if not members:
                continue

            is_afk = channel.id == afk_channel_id

            for member in members:
                others_not_muted = sum(
                    1
                    for other in members
                    if other.id != member.id and not other.voice.self_mute
                )
                eligible = is_eligible_for_voice_xp(
                    is_self_deaf=member.voice.self_deaf,
                    is_afk_channel=is_afk,
                    other_members_not_self_muted=others_not_muted,
                )
                grant = await leveling_repo.add_voice_minute(
                    guild.id, member.id, channel.id, is_eligible=eligible
                )
                if grant is not None and grant.leveled_up:
                    # Notifica mandata nel canale VOCALE stesso, non
                    # in un canale testuale a parte: i canali vocali
                    # moderni hanno la propria chat integrata
                    # (discord.VoiceChannel eredita da Messageable),
                    # ed è l'unico posto sensato per un task
                    # periodico che gira su più server insieme — a
                    # differenza dei messaggi testuali, non c'è un
                    # "canale in cui è appena successo qualcosa" da
                    # riusare.
                    try:
                        await channel.send(
                            f"🎉 {member.mention} è salito al livello "
                            f"**{grant.new_level}**!"
                        )
                    except discord.HTTPException:
                        pass

    # ================================================================
    # Comandi
    # ================================================================
    @app_commands.command(name="rank", description="Mostra il tuo livello e i tuoi coin.")
    @app_commands.describe(member="Il membro di cui vedere il livello (facoltativo)")
    async def rank(
        self, interaction: discord.Interaction, member: discord.Member | None = None
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return

        target = member or interaction.user
        totali = await leveling_repo.get_totals(interaction.guild.id, target.id)

        xp_livello_attuale = xp_for_level(totali.level)
        xp_prossimo_livello = xp_for_level(totali.level + 1)
        progresso = totali.xp_total - xp_livello_attuale
        richiesti = xp_prossimo_livello - xp_livello_attuale

        embed = discord.Embed(
            title=f"Livello di {target.display_name}",
            color=discord.Color.blurple(),
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name="Livello", value=str(totali.level), inline=True)
        embed.add_field(name="XP totale", value=str(totali.xp_total), inline=True)
        embed.add_field(name="Coin", value=str(totali.coins_total), inline=True)
        embed.add_field(
            name="Progresso al prossimo livello",
            value=f"{progresso}/{richiesti} XP",
            inline=False,
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="balance", description="Mostra i tuoi coin.")
    @app_commands.describe(member="Il membro di cui vedere il saldo (facoltativo)")
    async def balance(
        self, interaction: discord.Interaction, member: discord.Member | None = None
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return

        target = member or interaction.user
        totali = await leveling_repo.get_totals(interaction.guild.id, target.id)
        await interaction.response.send_message(
            f"{target.mention} ha **{totali.coins_total}** coin."
        )

    @app_commands.command(name="daily", description="Riscuoti la ricompensa giornaliera.")
    async def daily(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return

        totali = await leveling_repo.get_totals(interaction.guild.id, interaction.user.id)
        if not can_claim_daily(totali.last_daily_at):
            attesa = seconds_until_next_claim(totali.last_daily_at, 24 * 3600)
            await interaction.response.send_message(
                f"Hai già riscosso la ricompensa di oggi. Riprova tra {_format_seconds(attesa)}.",
                ephemeral=True,
            )
            return

        import datetime as _dt
        now = _dt.datetime.now(_dt.timezone.utc)
        await leveling_repo.add_coins(interaction.guild.id, interaction.user.id, DAILY_REWARD_COINS)
        await leveling_repo.set_last_daily(interaction.guild.id, interaction.user.id, now)
        await interaction.response.send_message(
            f"Hai riscosso **{DAILY_REWARD_COINS}** coin! Torna domani per altri."
        )

    @app_commands.command(name="work", description="Lavora per guadagnare qualche coin.")
    async def work(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return

        totali = await leveling_repo.get_totals(interaction.guild.id, interaction.user.id)
        if not can_claim_work(totali.last_work_at):
            attesa = seconds_until_next_claim(totali.last_work_at, 3600)
            await interaction.response.send_message(
                f"Sei stanco, riposati un po'. Riprova tra {_format_seconds(attesa)}.",
                ephemeral=True,
            )
            return

        import datetime as _dt
        import random
        now = _dt.datetime.now(_dt.timezone.utc)
        guadagno = random.randint(WORK_REWARD_MIN, WORK_REWARD_MAX)
        await leveling_repo.add_coins(interaction.guild.id, interaction.user.id, guadagno)
        await leveling_repo.set_last_work(interaction.guild.id, interaction.user.id, now)
        await interaction.response.send_message(f"Hai lavorato e guadagnato **{guadagno}** coin!")

    @app_commands.command(name="pay", description="Trasferisci coin a un altro utente.")
    @app_commands.describe(member="Chi riceve i coin", amount="Quanti coin trasferire")
    async def pay(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        amount: app_commands.Range[int, 1, None],
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return
        if member.id == interaction.user.id:
            await interaction.response.send_message(
                "Non puoi pagare te stesso.", ephemeral=True
            )
            return
        if member.bot:
            await interaction.response.send_message(
                "Non puoi pagare un bot.", ephemeral=True
            )
            return

        riuscito = await leveling_repo.transfer_coins(
            interaction.guild.id, interaction.user.id, member.id, amount
        )
        if not riuscito:
            await interaction.response.send_message(
                "Non hai abbastanza coin per questo trasferimento.", ephemeral=True
            )
            return

        await interaction.response.send_message(
            f"{interaction.user.mention} ha trasferito **{amount}** coin a {member.mention}."
        )

    # ================================================================
    # Classifiche
    # ================================================================
    @app_commands.command(name="leaderboard", description="Mostra la classifica del server.")
    @app_commands.describe(metric="XP o coin", period="Questo mese o di sempre")
    @app_commands.choices(
        metric=[
            app_commands.Choice(name="XP", value="xp"),
            app_commands.Choice(name="Coin", value="coins"),
        ],
        period=[
            app_commands.Choice(name="Questo mese", value="month"),
            app_commands.Choice(name="Di sempre", value="alltime"),
        ],
    )
    async def leaderboard(
        self,
        interaction: discord.Interaction,
        metric: app_commands.Choice[str],
        period: app_commands.Choice[str],
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return

        if metric.value == "xp" and period.value == "alltime":
            voci = await leveling_repo.top_xp_alltime(interaction.guild.id)
        elif metric.value == "xp":
            voci = await leveling_repo.top_xp_period(interaction.guild.id)
        elif metric.value == "coins" and period.value == "alltime":
            voci = await leveling_repo.top_coins_alltime(interaction.guild.id)
        else:
            voci = await leveling_repo.top_coins_period(interaction.guild.id)

        if not voci:
            await interaction.response.send_message(
                "Nessun dato ancora disponibile per questa classifica.", ephemeral=True
            )
            return

        medaglie = ["🥇", "🥈", "🥉"]
        righe = []
        for posizione, voce in enumerate(voci, start=1):
            prefisso = medaglie[posizione - 1] if posizione <= 3 else f"{posizione}."
            unita = "XP" if metric.value == "xp" else "coin"
            righe.append(f"{prefisso} <@{voce.user_id}> — **{voce.amount}** {unita}")

        embed = discord.Embed(
            title=f"Classifica {metric.name} — {period.name}",
            description="\n".join(righe),
            color=discord.Color.gold(),
        )
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot) -> None:
    registry.register(
        PremiumModule(
            name=MODULE_LEVELING,
            display_name="Livelli & Economia",
            description="XP, livelli, daily/work/pay, classifiche mensili e all-time.",
            premium_capable=False,
        )
    )
    await bot.add_cog(LevelingCog(bot))
