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
import random
from datetime import datetime, timedelta, timezone
from typing import Literal

import discord
from discord import app_commands
from discord.ext import commands, tasks

from core.database import db
from core.repositories.leveling_repo import leveling_repo
from core.repositories.level_reward_repo import level_reward_repo
from core.monthly_winners_logic import MEDALS, previous_period_key
from core.repositories.monthly_winners_repo import monthly_winners_repo
from core.repositories.shop_repo import shop_repo
from core.drop_logic import DEFAULT_MAX_COINS, DEFAULT_MIN_COINS, should_trigger_drop
from core.giveaway_logic import is_eligible, pick_winners
from core.repositories.giveaway_repo import giveaway_repo
from core.premium_pricing_logic import TIER_MONTHS_REQUIRED
from core.premium_purchase_service import PurchaseOutcome, purchase_premium_tier
from core.repositories.guild_chest_repo import guild_chest_repo
from core.guild_clan_logic import (
    CREATION_DEFICIT,
    CREATION_GRACE_HOURS,
    MAX_ADMINS_PER_CLAN,
    MAX_MODS_PER_CLAN,
    is_creation_deficit_covered,
    validate_guild_tag,
)
from core.repositories.guild_clan_repo import (
    ROLE_ADMIN,
    ROLE_MEMBER,
    ROLE_MOD,
    ROLE_OWNER,
    guild_clan_repo,
)
from core.guild_clan_role_service import (
    clear_member_clan_presence,
    sync_member_clan_role,
)
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
    async def _grant_level_rewards(
        self, member: discord.Member, guild: discord.Guild, new_level: int
    ) -> None:
        """
        Condiviso tra XP testuale e vocale (SPEC.md §15.13) — un
        solo punto che assegna i ruoli-premio, non due copie della
        stessa logica. Salta i ruoli che il membro ha già (un
        re-invio ripetuto non deve fallire né generare richieste
        Discord inutili).
        """
        ricompense = await level_reward_repo.get_rewards_up_to_level(guild.id, new_level)
        if not ricompense:
            return

        id_ruoli_posseduti = {ruolo.id for ruolo in member.roles}
        da_assegnare = [
            discord.Object(id=r.role_id) for r in ricompense if r.role_id not in id_ruoli_posseduti
        ]
        if not da_assegnare:
            return

        try:
            await member.add_roles(
                *da_assegnare, reason=f"Ruolo-premio per aver raggiunto il livello {new_level}"
            )
        except discord.HTTPException:
            logger.warning(
                "Impossibile assegnare i ruoli-premio a %s nel server %s.", member.id, guild.id
            )

    class DropClaimView(discord.ui.View):
        """
        "Primo che clicca vince" — self.claimed_by è lo stato
        condiviso in memoria per QUESTO drop specifico (un'istanza
        per drop, non persistita: se il bot si riavvia mentre un
        drop è ancora aperto, va semplicemente perso, accettabile
        per una piccola sorpresa occasionale).
        """

        def __init__(self, guild_id: int, amount: int) -> None:
            super().__init__(timeout=120)
            self.guild_id = guild_id
            self.amount = amount
            self.claimed_by: int | None = None

        @discord.ui.button(label="Raccogli", emoji="💰", style=discord.ButtonStyle.success)
        async def raccogli(
            self, interaction: discord.Interaction, button: discord.ui.Button
        ) -> None:
            if self.claimed_by is not None:
                await interaction.response.send_message(
                    "Questo drop è già stato raccolto.", ephemeral=True
                )
                return

            self.claimed_by = interaction.user.id
            await leveling_repo.add_coins(self.guild_id, interaction.user.id, self.amount)

            button.disabled = True
            button.label = f"Raccolto da {interaction.user.display_name}"
            await interaction.response.edit_message(view=self)

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
            await self._grant_level_rewards(message.author, message.guild, risultato.new_level)

        if should_trigger_drop(random.random()):
            importo = random.randint(DEFAULT_MIN_COINS, DEFAULT_MAX_COINS)
            view = self.DropClaimView(message.guild.id, importo)
            try:
                await message.channel.send(
                    f"💰 È apparso un drop di **{importo}** coin! Clicca per raccoglierlo.",
                    view=view,
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
                    await self._grant_level_rewards(member, guild, grant.new_level)

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

        righe = []
        for posizione, voce in enumerate(voci, start=1):
            prefisso = MEDALS[posizione - 1] if posizione <= len(MEDALS) else f"{posizione}."
            unita = "XP" if metric.value == "xp" else "coin"
            righe.append(f"{prefisso} <@{voce.user_id}> — **{voce.amount}** {unita}")

        embed = discord.Embed(
            title=f"Classifica {metric.name} — {period.name}",
            description="\n".join(righe),
            color=discord.Color.gold(),
        )
        await interaction.response.send_message(embed=embed)

    # ================================================================
    # Ruoli-premio (SPEC.md §15.13)
    # ================================================================
    level_roles_group = app_commands.Group(
        name="level-roles", description="[Admin] Gestisce i ruoli assegnati automaticamente per livello."
    )

    @level_roles_group.command(
        name="add", description="[Admin] Assegna un ruolo a chi raggiunge un livello."
    )
    @app_commands.describe(
        level="Livello richiesto", role="Ruolo da assegnare al raggiungimento"
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def level_roles_add(
        self, interaction: discord.Interaction, level: app_commands.Range[int, 1, 1000], role: discord.Role
    ) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return

        await level_reward_repo.add_reward(guild.id, level_threshold=level, role_id=role.id)
        await interaction.response.send_message(
            f"✅ Chi raggiunge il livello **{level}** riceverà il ruolo {role.mention}.",
            ephemeral=True,
        )

    @level_roles_group.command(
        name="remove", description="[Admin] Rimuove un ruolo-premio configurato."
    )
    @app_commands.describe(reward_id="ID della ricompensa (vedi /level-roles list)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def level_roles_remove(self, interaction: discord.Interaction, reward_id: int) -> None:
        guild = interaction.guild
        if guild is None:
            return

        rimossa = await level_reward_repo.remove_reward(reward_id, guild.id)
        if rimossa:
            await interaction.response.send_message("Ruolo-premio rimosso.", ephemeral=True)
        else:
            await interaction.response.send_message(
                "Nessun ruolo-premio trovato con questo ID in questo server.", ephemeral=True
            )

    @level_roles_group.command(
        name="list", description="[Admin] Mostra i ruoli-premio configurati su questo server."
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def level_roles_list(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None:
            return

        ricompense = await level_reward_repo.list_rewards(guild.id)
        if not ricompense:
            await interaction.response.send_message(
                "Nessun ruolo-premio configurato su questo server.", ephemeral=True
            )
            return

        righe = [f"`{r.id}` livello **{r.level_threshold}** → <@&{r.role_id}>" for r in ricompense]
        embed = discord.Embed(
            title="🏅 Ruoli-premio configurati",
            description="\n".join(righe),
            color=discord.Color.gold(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


    # ================================================================
    # Annuncio vincitori mensile (SPEC.md §15.11)
    # ================================================================
    monthly_winners_group = app_commands.Group(
        name="monthly-winners",
        description="[Admin] Annuncio automatico dei vincitori a fine mese.",
    )

    @monthly_winners_group.command(
        name="set", description="[Admin] Imposta il canale dove annunciare i vincitori del mese."
    )
    @app_commands.describe(channel="Canale dell'annuncio")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def monthly_winners_set(
        self, interaction: discord.Interaction, channel: discord.TextChannel
    ) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return

        await monthly_winners_repo.set_channel(
            guild.id, channel.id, already_covered_period=previous_period_key()
        )
        await interaction.response.send_message(
            f"✅ I vincitori del mese verranno annunciati in {channel.mention} "
            f"all'inizio di ogni mese (il primo annuncio al prossimo cambio mese).",
            ephemeral=True,
        )

    @monthly_winners_group.command(
        name="disable", description="[Admin] Disattiva l'annuncio dei vincitori del mese."
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def monthly_winners_disable(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None:
            return

        if await monthly_winners_repo.disable(guild.id):
            await interaction.response.send_message("Annuncio mensile disattivato.", ephemeral=True)
        else:
            await interaction.response.send_message(
                "L'annuncio mensile non era attivo su questo server.", ephemeral=True
            )

    # ================================================================
    # Shop (SPEC.md §15.4)
    # ================================================================
    shop_group = app_commands.Group(
        name="shop", description="Negozio: spendi i tuoi coin su oggetti o ruoli."
    )

    @shop_group.command(name="list", description="Mostra gli oggetti disponibili nello shop.")
    async def shop_list(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return

        oggetti = await shop_repo.list_items(guild.id)
        if not oggetti:
            await interaction.response.send_message(
                "Lo shop di questo server è vuoto.", ephemeral=True
            )
            return

        righe = []
        for oggetto in oggetti:
            riga = f"`{oggetto.id}` **{oggetto.name}** — {oggetto.price} coin"
            if oggetto.role_id is not None:
                riga += f" (ruolo <@&{oggetto.role_id}>)"
            if oggetto.description:
                riga += f"\n> {oggetto.description}"
            righe.append(riga)

        embed = discord.Embed(
            title="🛒 Shop", description="\n".join(righe), color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed)

    @shop_group.command(name="buy", description="Acquista un oggetto dello shop.")
    @app_commands.describe(item_id="ID dell'oggetto (vedi /shop list)")
    async def shop_buy(self, interaction: discord.Interaction, item_id: int) -> None:
        guild = interaction.guild
        if guild is None or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return

        oggetto = await shop_repo.get_item(item_id, guild.id)
        if oggetto is None:
            await interaction.response.send_message(
                "Nessun oggetto trovato con questo ID.", ephemeral=True
            )
            return

        if oggetto.role_id is not None and await shop_repo.has_purchased(
            guild.id, interaction.user.id, oggetto.id
        ):
            await interaction.response.send_message(
                "Hai già acquistato questo oggetto.", ephemeral=True
            )
            return

        riuscito = await leveling_repo.spend_coins(guild.id, interaction.user.id, oggetto.price)
        if not riuscito:
            await interaction.response.send_message(
                f"Non hai abbastanza coin — servono **{oggetto.price}**.", ephemeral=True
            )
            return

        await shop_repo.record_purchase(guild.id, interaction.user.id, oggetto.id)

        if oggetto.role_id is not None:
            try:
                await interaction.user.add_roles(
                    discord.Object(id=oggetto.role_id), reason=f"Acquisto shop: {oggetto.name}"
                )
            except discord.HTTPException:
                logger.warning(
                    "Impossibile assegnare il ruolo shop %s a %s.",
                    oggetto.role_id,
                    interaction.user.id,
                )

        await interaction.response.send_message(
            f"✅ Hai acquistato **{oggetto.name}** per {oggetto.price} coin!"
        )

    @shop_group.command(name="add-item", description="[Admin] Aggiunge un oggetto allo shop.")
    @app_commands.describe(
        name="Nome dell'oggetto",
        price="Prezzo in coin",
        role="Ruolo da assegnare all'acquisto (facoltativo)",
        description="Descrizione (facoltativa)",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def shop_add_item(
        self,
        interaction: discord.Interaction,
        name: str,
        price: app_commands.Range[int, 1, 1000000],
        role: discord.Role | None = None,
        description: str | None = None,
    ) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return

        item_id = await shop_repo.add_item(
            guild.id, name=name, price=price,
            role_id=role.id if role else None, description=description,
        )
        await interaction.response.send_message(
            f"✅ Aggiunto **{name}** allo shop (ID `{item_id}`).", ephemeral=True
        )

    @shop_group.command(
        name="remove-item", description="[Admin] Rimuove un oggetto dallo shop."
    )
    @app_commands.describe(item_id="ID dell'oggetto (vedi /shop list)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def shop_remove_item(self, interaction: discord.Interaction, item_id: int) -> None:
        guild = interaction.guild
        if guild is None:
            return

        if await shop_repo.remove_item(item_id, guild.id):
            await interaction.response.send_message("Oggetto rimosso dallo shop.", ephemeral=True)
        else:
            await interaction.response.send_message(
                "Nessun oggetto trovato con questo ID in questo server.", ephemeral=True
            )

    # ================================================================
    # Cassa di server (SPEC.md §15.15) — alimentata dal decadimento
    # settimanale sui coin personali e da quello mensile della
    # tesoreria di clan, usabile per premi evento e per lo sblocco
    # del bot premium (doppio cancello: tempo dal join del bot +
    # costo in coin, variabile per fascia membri).
    # ================================================================

    chest_group = app_commands.Group(
        name="cassa", description="Cassa del server: saldo, ledger e sblocco premium."
    )

    @chest_group.command(name="saldo", description="Mostra il saldo della cassa del server.")
    async def chest_saldo(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return

        saldo = await guild_chest_repo.get_balance(guild.id)
        movimenti = await guild_chest_repo.list_ledger(guild.id, limit=5)

        embed = discord.Embed(
            title="🏛️ Cassa del server",
            description=f"Saldo attuale: **{saldo}** coin",
            color=discord.Color.gold(),
        )
        if movimenti:
            righe = []
            for m in movimenti:
                segno = "+" if m.amount > 0 else ""
                righe.append(f"`{m.created_at:%Y-%m-%d}` {segno}{m.amount} — {m.reason}")
            embed.add_field(name="Ultimi movimenti", value="\n".join(righe), inline=False)
        await interaction.response.send_message(embed=embed)

    @chest_group.command(
        name="sblocca-premium",
        description="[Admin] Sblocca un mese di bot premium spendendo dalla cassa.",
    )
    @app_commands.describe(
        tier="Quale mese sbloccare: 1° (dopo 6 mesi), 2° (dopo 1 anno) o 3° (dopo 2 anni)"
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def chest_sblocca_premium(
        self, interaction: discord.Interaction, tier: app_commands.Range[int, 1, 3]
    ) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return

        risultato = await purchase_premium_tier(
            guild.id, tier=tier, member_count=guild.member_count or 0
        )

        if risultato.outcome == PurchaseOutcome.GUILD_NOT_CONFIGURED:
            await interaction.response.send_message(
                "Configurazione del server non trovata — riprova più tardi.", ephemeral=True
            )
        elif risultato.outcome == PurchaseOutcome.ALREADY_PURCHASED:
            await interaction.response.send_message(
                f"Il {tier}° mese di premium è già stato acquistato da questo server.",
                ephemeral=True,
            )
        elif risultato.outcome == PurchaseOutcome.TIME_NOT_UNLOCKED:
            mesi_richiesti = TIER_MONTHS_REQUIRED[tier]
            await interaction.response.send_message(
                f"Il {tier}° mese di premium si sblocca solo dopo {mesi_richiesti} mesi "
                "dall'ingresso del bot in questo server — non è ancora passato abbastanza tempo.",
                ephemeral=True,
            )
        elif risultato.outcome == PurchaseOutcome.INSUFFICIENT_FUNDS:
            await interaction.response.send_message(
                f"La cassa non basta — servono **{risultato.cost}** coin per il {tier}° mese.",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                f"✅ {tier}° mese di premium sbloccato per **{risultato.cost}** coin dalla "
                f"cassa! Premium attivo fino al {risultato.new_premium_until:%Y-%m-%d}."
            )

    # ================================================================
    # Sistema Gilde/Clan (SPEC.md §15.14) — primo pezzo di comandi:
    # crea, info, membri, classifica, tesoreria/dona, sciogli. Il
    # motore economico (tick vocale, decadimento, XP) è già completo
    # a livello di repository/worker da prima — qui arrivano i primi
    # comandi Discord per usarlo davvero. Inviti/espulsioni/
    # promozioni, acquisto canali e boost restano il pezzo successivo.
    # ================================================================

    clan_group = app_commands.Group(
        name="clan", description="Sistema Gilde/Clan: crea, gestisci, dona alla tesoreria."
    )

    @clan_group.command(name="crea", description="Crea una nuova gilda/clan.")
    @app_commands.describe(
        tag=f"Tag della gilda (1-5 caratteri, niente emoji né spazi)",
        name="Nome completo della gilda",
    )
    async def clan_crea(self, interaction: discord.Interaction, tag: str, name: str) -> None:
        guild = interaction.guild
        if guild is None or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return

        valido, motivo = validate_guild_tag(tag)
        if not valido:
            await interaction.response.send_message(motivo, ephemeral=True)
            return

        if await guild_clan_repo.get_member_clan_in_guild(guild.id, interaction.user.id):
            await interaction.response.send_message(
                "Fai già parte di una gilda in questo server — lasciala prima di crearne una nuova.",
                ephemeral=True,
            )
            return

        if await guild_clan_repo.is_tag_taken(guild.id, tag):
            await interaction.response.send_message(
                f"Il tag `{tag}` è già usato da un'altra gilda in questo server.",
                ephemeral=True,
            )
            return

        try:
            categoria = await guild.create_category(
                name=f"[{tag}] {name}"[:100],
                overwrites={
                    guild.default_role: discord.PermissionOverwrite(view_channel=False),
                    interaction.user: discord.PermissionOverwrite(
                        view_channel=True, send_messages=True, manage_channels=True
                    ),
                    guild.me: discord.PermissionOverwrite(
                        view_channel=True, send_messages=True, manage_channels=True
                    ),
                },
                reason=f"Creazione gilda '{tag}' da {interaction.user}",
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "Non ho i permessi per creare una categoria in questo server.", ephemeral=True
            )
            return
        except discord.HTTPException:
            await interaction.response.send_message(
                "Creazione della categoria fallita — riprova più tardi.", ephemeral=True
            )
            return

        scadenza = datetime.now(timezone.utc) + timedelta(hours=CREATION_GRACE_HOURS)
        clan_id = await guild_clan_repo.create_clan(
            guild.id, tag=tag, name=name, owner_id=interaction.user.id,
            officialize_deadline=scadenza,
        )
        await guild_clan_repo.set_category_id(clan_id, categoria.id)
        await sync_member_clan_role(guild, categoria, interaction.user, ROLE_OWNER)

        await interaction.response.send_message(
            f"✅ Gilda **{name}** (`{tag}`) creata! Per ufficializzarla servono "
            f"**{CREATION_DEFICIT}** coin in tesoreria entro **{CREATION_GRACE_HOURS} ore** "
            f"(`/clan tesoreria dona`) — altrimenti verrà eliminata automaticamente."
        )

    @clan_group.command(name="info", description="Mostra le informazioni di una gilda.")
    @app_commands.describe(tag="Tag della gilda (facoltativo: la tua, se non specificato)")
    async def clan_info(self, interaction: discord.Interaction, tag: str | None = None) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return

        if tag is not None:
            clan = await guild_clan_repo.get_clan_by_tag(guild.id, tag)
        else:
            clan = await guild_clan_repo.get_member_clan_in_guild(guild.id, interaction.user.id)

        if clan is None:
            await interaction.response.send_message(
                "Nessuna gilda trovata." if tag else "Non fai parte di nessuna gilda in questo server.",
                ephemeral=True,
            )
            return

        n_membri = await guild_clan_repo.count_members(clan.id)
        stato = "✅ Ufficializzata" if clan.officialized else (
            f"⏳ In attesa (scade <t:{int(clan.officialize_deadline.timestamp())}:R>)"
        )

        embed = discord.Embed(
            title=f"🛡️ [{clan.tag}] {clan.name}", color=discord.Color.blurple()
        )
        embed.add_field(name="Stato", value=stato, inline=False)
        embed.add_field(name="Capo Clan", value=f"<@{clan.owner_id}>", inline=True)
        if clan.co_owner_id is not None:
            embed.add_field(name="Co-Owner", value=f"<@{clan.co_owner_id}>", inline=True)
        embed.add_field(name="Membri", value=f"{n_membri}/{clan.max_members}", inline=True)
        embed.add_field(name="Tesoreria", value=f"{clan.treasury_balance} coin", inline=True)
        embed.add_field(name="XP totale", value=str(clan.total_xp), inline=True)
        embed.add_field(name="Canali sbloccati", value=str(clan.channels_unlocked), inline=True)
        await interaction.response.send_message(embed=embed)

    @clan_group.command(name="membri", description="Mostra i membri di una gilda.")
    @app_commands.describe(tag="Tag della gilda (facoltativo: la tua, se non specificato)")
    async def clan_membri(self, interaction: discord.Interaction, tag: str | None = None) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return

        if tag is not None:
            clan = await guild_clan_repo.get_clan_by_tag(guild.id, tag)
        else:
            clan = await guild_clan_repo.get_member_clan_in_guild(guild.id, interaction.user.id)

        if clan is None:
            await interaction.response.send_message(
                "Nessuna gilda trovata." if tag else "Non fai parte di nessuna gilda in questo server.",
                ephemeral=True,
            )
            return

        membri = await guild_clan_repo.list_members(clan.id)
        righe = [f"<@{m.user_id}> — {m.role}" for m in membri]
        embed = discord.Embed(
            title=f"Membri di [{clan.tag}] {clan.name}",
            description="\n".join(righe) if righe else "Nessun membro.",
            color=discord.Color.blurple(),
        )
        await interaction.response.send_message(embed=embed)

    @clan_group.command(name="classifica", description="Classifica delle gilde per XP totale.")
    async def clan_classifica(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return

        classifica = await guild_clan_repo.get_clan_leaderboard(guild.id)
        if not classifica:
            await interaction.response.send_message(
                "Nessuna gilda in questo server ancora.", ephemeral=True
            )
            return

        righe = [
            f"**{i+1}.** [{c.tag}] {c.name} — {c.total_xp} XP"
            for i, c in enumerate(classifica)
        ]
        embed = discord.Embed(
            title="🏆 Classifica Gilde", description="\n".join(righe), color=discord.Color.gold()
        )
        await interaction.response.send_message(embed=embed)

    @clan_group.command(name="sciogli", description="[Capo Clan] Sciogli la tua gilda.")
    async def clan_sciogli(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return

        clan = await guild_clan_repo.get_member_clan_in_guild(guild.id, interaction.user.id)
        if clan is None:
            await interaction.response.send_message(
                "Non fai parte di nessuna gilda in questo server.", ephemeral=True
            )
            return
        if clan.owner_id != interaction.user.id:
            await interaction.response.send_message(
                "Solo il Capo Clan può sciogliere la gilda.", ephemeral=True
            )
            return

        categoria = None
        if clan.category_id is not None:
            categoria = guild.get_channel(clan.category_id)

        # Il Capo Clan è sempre chi chiama questo comando (controllo
        # sopra): il suo ruolo/overwrite si puliscono con l'oggetto
        # Member già in mano. Per gli altri ufficiali (Admin Clan) non
        # necessariamente in cache, la pulizia dei loro overwrite è
        # comunque implicita nella cancellazione della categoria; solo
        # il ruolo condiviso può restarci — accettabile per un clan
        # sciolto, verrà rimosso automaticamente alla prossima
        # promozione/espulsione altrove.
        await clear_member_clan_presence(guild, categoria, interaction.user)

        if categoria is not None:
            for canale in list(categoria.channels):
                try:
                    await canale.delete(reason=f"Gilda '{clan.tag}' sciolta")
                except discord.HTTPException:
                    logger.warning("Impossibile eliminare il canale %s della gilda %s.", canale.id, clan.id)
            try:
                await categoria.delete(reason=f"Gilda '{clan.tag}' sciolta")
            except discord.HTTPException:
                logger.warning("Impossibile eliminare la categoria della gilda %s.", clan.id)

        await guild_clan_repo.delete_clan(clan.id)
        await interaction.response.send_message(f"La gilda **{clan.name}** è stata sciolta.")

    @clan_group.command(name="invita", description="[Capo/Admin Clan] Invita un membro nella tua gilda.")
    @app_commands.describe(membro="Il membro da invitare nella tua gilda")
    async def clan_invita(self, interaction: discord.Interaction, membro: discord.Member) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return

        clan = await guild_clan_repo.get_member_clan_in_guild(guild.id, interaction.user.id)
        if clan is None:
            await interaction.response.send_message(
                "Non fai parte di nessuna gilda in questo server.", ephemeral=True
            )
            return

        chi_invita = await guild_clan_repo.get_member(clan.id, interaction.user.id)
        if chi_invita is None or chi_invita.role not in (ROLE_OWNER, ROLE_ADMIN):
            await interaction.response.send_message(
                "Solo il Capo Clan o un Admin Clan possono invitare nuovi membri.", ephemeral=True
            )
            return

        if await guild_clan_repo.get_member_clan_in_guild(guild.id, membro.id) is not None:
            await interaction.response.send_message(
                f"{membro.mention} fa già parte di una gilda in questo server.", ephemeral=True
            )
            return

        if await guild_clan_repo.count_members(clan.id) >= clan.max_members:
            await interaction.response.send_message(
                f"La gilda ha già raggiunto il limite di **{clan.max_members}** membri.", ephemeral=True
            )
            return

        await guild_clan_repo.add_member(clan.id, membro.id, role=ROLE_MEMBER)

        categoria = guild.get_channel(clan.category_id) if clan.category_id is not None else None
        await sync_member_clan_role(guild, categoria, membro, ROLE_MEMBER)

        await interaction.response.send_message(
            f"✅ {membro.mention} è stato invitato in **{clan.name}**."
        )

    @clan_group.command(name="espelli", description="[Capo/Admin Clan] Espelli un membro dalla tua gilda.")
    @app_commands.describe(membro="Il membro da espellere dalla tua gilda")
    async def clan_espelli(self, interaction: discord.Interaction, membro: discord.Member) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return

        clan = await guild_clan_repo.get_member_clan_in_guild(guild.id, interaction.user.id)
        if clan is None:
            await interaction.response.send_message(
                "Non fai parte di nessuna gilda in questo server.", ephemeral=True
            )
            return

        chi_espelle = await guild_clan_repo.get_member(clan.id, interaction.user.id)
        if chi_espelle is None or chi_espelle.role not in (ROLE_OWNER, ROLE_ADMIN):
            await interaction.response.send_message(
                "Solo il Capo Clan o un Admin Clan possono espellere membri.", ephemeral=True
            )
            return

        target = await guild_clan_repo.get_member(clan.id, membro.id)
        if target is None:
            await interaction.response.send_message(
                f"{membro.mention} non fa parte della tua gilda.", ephemeral=True
            )
            return

        if membro.id == clan.owner_id:
            await interaction.response.send_message(
                "Il Capo Clan non può essere espulso — usa `/clan sciogli` per sciogliere la gilda.",
                ephemeral=True,
            )
            return

        if chi_espelle.role == ROLE_ADMIN and target.role == ROLE_ADMIN:
            await interaction.response.send_message(
                "Un Admin Clan non può espellere un altro Admin Clan — serve il Capo Clan.",
                ephemeral=True,
            )
            return

        await guild_clan_repo.remove_member(clan.id, membro.id)

        categoria = guild.get_channel(clan.category_id) if clan.category_id is not None else None
        await clear_member_clan_presence(guild, categoria, membro)

        await interaction.response.send_message(
            f"✅ {membro.mention} è stato espulso da **{clan.name}**."
        )

    @clan_group.command(name="promuovi", description="[Capo Clan] Cambia il ruolo di un membro della tua gilda.")
    @app_commands.describe(membro="Il membro a cui cambiare ruolo", ruolo="Il nuovo ruolo da assegnare")
    async def clan_promuovi(
        self,
        interaction: discord.Interaction,
        membro: discord.Member,
        ruolo: Literal["admin", "mod", "member"],
    ) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return

        clan = await guild_clan_repo.get_member_clan_in_guild(guild.id, interaction.user.id)
        if clan is None:
            await interaction.response.send_message(
                "Non fai parte di nessuna gilda in questo server.", ephemeral=True
            )
            return

        if clan.owner_id != interaction.user.id:
            await interaction.response.send_message(
                "Solo il Capo Clan può cambiare il ruolo dei membri.", ephemeral=True
            )
            return

        if membro.id == clan.owner_id:
            await interaction.response.send_message(
                "Il Capo Clan non può cambiare il proprio ruolo.", ephemeral=True
            )
            return

        target = await guild_clan_repo.get_member(clan.id, membro.id)
        if target is None:
            await interaction.response.send_message(
                f"{membro.mention} non fa parte della tua gilda.", ephemeral=True
            )
            return

        if ruolo == ROLE_ADMIN and target.role != ROLE_ADMIN:
            if await guild_clan_repo.count_members_with_role(clan.id, ROLE_ADMIN) >= MAX_ADMINS_PER_CLAN:
                await interaction.response.send_message(
                    f"La gilda ha già raggiunto il limite di **{MAX_ADMINS_PER_CLAN}** Admin Clan.",
                    ephemeral=True,
                )
                return
        elif ruolo == ROLE_MOD and target.role != ROLE_MOD:
            if await guild_clan_repo.count_members_with_role(clan.id, ROLE_MOD) >= MAX_MODS_PER_CLAN:
                await interaction.response.send_message(
                    f"La gilda ha già raggiunto il limite di **{MAX_MODS_PER_CLAN}** Mod Clan.",
                    ephemeral=True,
                )
                return

        await guild_clan_repo.set_member_role(clan.id, membro.id, ruolo)

        categoria = guild.get_channel(clan.category_id) if clan.category_id is not None else None
        await sync_member_clan_role(guild, categoria, membro, ruolo)

        await interaction.response.send_message(
            f"✅ {membro.mention} è ora **{ruolo}** in **{clan.name}**."
        )

    clan_tesoreria_group = app_commands.Group(
        name="tesoreria", description="Tesoreria della tua gilda.", parent=clan_group
    )

    @clan_tesoreria_group.command(name="dona", description="Dona coin personali alla tesoreria della tua gilda.")
    @app_commands.describe(importo="Quante coin donare (dal tuo saldo personale)")
    async def clan_tesoreria_dona(
        self, interaction: discord.Interaction, importo: app_commands.Range[int, 1, 1_000_000_000]
    ) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return

        clan = await guild_clan_repo.get_member_clan_in_guild(guild.id, interaction.user.id)
        if clan is None:
            await interaction.response.send_message(
                "Non fai parte di nessuna gilda in questo server.", ephemeral=True
            )
            return

        riuscito = await leveling_repo.spend_coins(guild.id, interaction.user.id, importo)
        if not riuscito:
            await interaction.response.send_message(
                f"Non hai abbastanza coin personali — servono **{importo}**.", ephemeral=True
            )
            return

        nuovo_saldo = await guild_clan_repo.donate(clan.id, interaction.user.id, importo)

        messaggio = f"✅ Hai donato **{importo}** coin alla tesoreria di **{clan.name}** (saldo: {nuovo_saldo})."
        if not clan.officialized and is_creation_deficit_covered(nuovo_saldo):
            await guild_clan_repo.set_officialized(clan.id)
            messaggio += "\n🎉 Il deficit di creazione è coperto: la gilda è ora **ufficializzata**!"

        await interaction.response.send_message(messaggio)

    # ================================================================
    # Giveaway (SPEC.md §15.5, con requisiti di ruolo/livello)
    # ================================================================
    class GiveawayEnterView(discord.ui.View):
        """
        PERSISTENTE (timeout=None, custom_id fisso che incorpora
        l'ID del giveaway) — un giveaway dura ore o giorni, deve
        continuare a funzionare anche dopo un riavvio del bot.
        main.py la ri-registra per ogni giveaway ancora attivo ad
        ogni avvio (bot.add_view), altrimenti i pulsanti dei
        messaggi già inviati smetterebbero di rispondere.
        """

        def __init__(self, giveaway_id: int) -> None:
            super().__init__(timeout=None)
            self._entra.custom_id = f"giveaway_enter:{giveaway_id}"
            self.giveaway_id = giveaway_id

        @discord.ui.button(label="Partecipa", emoji="🎉", style=discord.ButtonStyle.primary)
        async def _entra(
            self, interaction: discord.Interaction, button: discord.ui.Button
        ) -> None:
            giveaway = await giveaway_repo.get_giveaway(self.giveaway_id)
            if giveaway is None or giveaway.ended:
                await interaction.response.send_message(
                    "Questo giveaway non è più attivo.", ephemeral=True
                )
                return

            totali = await leveling_repo.get_totals(giveaway.guild_id, interaction.user.id)
            ruoli_utente = {r.id for r in interaction.user.roles}
            if not is_eligible(
                totali.level, ruoli_utente, giveaway.min_level, giveaway.required_role_id
            ):
                requisiti = []
                if giveaway.min_level > 0:
                    requisiti.append(f"livello {giveaway.min_level}")
                if giveaway.required_role_id is not None:
                    requisiti.append(f"il ruolo <@&{giveaway.required_role_id}>")
                await interaction.response.send_message(
                    f"Non soddisfi i requisiti per partecipare (richiesto: {', '.join(requisiti)}).",
                    ephemeral=True,
                )
                return

            nuova = await giveaway_repo.add_entry(self.giveaway_id, interaction.user.id)
            if nuova:
                await interaction.response.send_message(
                    "✅ Partecipazione registrata, in bocca al lupo!", ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    "Avevi già partecipato a questo giveaway.", ephemeral=True
                )

    @app_commands.command(name="giveaway", description="[Admin] Avvia un giveaway.")
    @app_commands.describe(
        prize="Cosa si vince",
        duration_minutes="Durata in minuti",
        winners="Numero di vincitori (default 1)",
        min_level="Livello minimo richiesto (facoltativo)",
        required_role="Ruolo richiesto per partecipare (facoltativo)",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def giveaway(
        self,
        interaction: discord.Interaction,
        prize: str,
        duration_minutes: app_commands.Range[int, 1, 43200],
        winners: app_commands.Range[int, 1, 50] = 1,
        min_level: app_commands.Range[int, 0, 1000] = 0,
        required_role: discord.Role | None = None,
    ) -> None:
        guild = interaction.guild
        if guild is None or interaction.channel is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return

        scadenza = datetime.now(timezone.utc) + timedelta(minutes=duration_minutes)

        giveaway_id = await giveaway_repo.create_giveaway(
            guild.id, interaction.channel.id, prize, winners, min_level,
            required_role.id if required_role else None, scadenza, interaction.user.id,
        )

        requisiti = []
        if min_level > 0:
            requisiti.append(f"livello **{min_level}**")
        if required_role is not None:
            requisiti.append(f"ruolo {required_role.mention}")
        riga_requisiti = f"\nRequisiti: {', '.join(requisiti)}" if requisiti else ""

        embed = discord.Embed(
            title=f"🎉 Giveaway: {prize}",
            description=(
                f"Vincitori: **{winners}**\n"
                f"Termina: <t:{int(scadenza.timestamp())}:R>{riga_requisiti}"
            ),
            color=discord.Color.blurple(),
        )

        view = self.GiveawayEnterView(giveaway_id)
        await interaction.response.send_message(embed=embed, view=view)
        messaggio = await interaction.original_response()
        await giveaway_repo.set_message_id(giveaway_id, messaggio.id)

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
