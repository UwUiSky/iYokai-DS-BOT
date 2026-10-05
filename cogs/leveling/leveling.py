"""
cogs/leveling/leveling.py
============================
XP testuale (on_message) e vocale (task periodico ogni 60s), livelli,
economia (daily/work/pay/balance, shop, drop, giveaway), cassa del
server, gilde/clan, classifiche mensili e di sempre. Modulo sempre
gratuito.
Funzioni coperte: SPEC §15

Message Content Intent: è attivo (vedi main.py), ma questo modulo non
legge mai message.content: gli basta sapere CHE un messaggio è stato
inviato, non cosa dice.

L'XP vocale usa un task periodico (tasks.loop) e non l'evento
on_voice_state_update: l'XP si accumula minuto per minuto per tutta
la permanenza in vocale, non solo quando si entra o si esce.
"""

# DA FARE (issue #65, fase F1): correzioni aperte per questo file in
#   revisione/02-piano/MODIFICHE_ESISTENTE.md §9 (Livelli, economia,
#   clan).
# DA FARE (issue #83, fase F9): NF-12, Rank card. Vedi
#   revisione/02-piano/NUOVE_FUNZIONI.md.
# DA FARE (issue #86, fase F9): NF-15, Impostazioni dei livelli. Vedi
#   revisione/02-piano/NUOVE_FUNZIONI.md.
# DA FARE (issue #99, fase F13): NF-28, Giveaway avanzati. Vedi
#   revisione/02-piano/NUOVE_FUNZIONI.md.

from __future__ import annotations

import logging
import random
from datetime import datetime, timedelta, timezone
from typing import Literal

import discord
from discord import app_commands
from discord.ext import commands, tasks

from core.database import db
from core.role_safety import check_role_assignable
from core.repositories.blacklist_repo import blacklist_repo
from core.repositories.leveling_repo import leveling_repo
from core.repositories.level_reward_repo import level_reward_repo
from core.monthly_winners_logic import MEDALS, previous_period_key
from core.ui_base import BaseView
from cogs.leveling._pagine import invia_lista, taglia
from core.repositories.monthly_winners_repo import monthly_winners_repo
from core.clan_leaderboard_logic import previous_period_key as clan_previous_period_key
from core.repositories.clan_leaderboard_config_repo import clan_leaderboard_config_repo
from core.repositories.shop_repo import EsitoAcquisto, shop_repo
from core.drop_logic import DEFAULT_MAX_COINS, DEFAULT_MIN_COINS, should_trigger_drop
from core.giveaway_logic import is_eligible, pick_winners
from core.repositories.giveaway_repo import giveaway_repo
from core.premium_pricing_logic import TIER_MONTHS_REQUIRED
from core.premium_purchase_service import PurchaseOutcome, purchase_premium_tier
from core.repositories.guild_chest_repo import (
    REASON_EVENT_LOBBY_PRIZE,
    REASON_EVENT_WINNER_PRIZE,
    guild_chest_repo,
)
from core.guild_clan_logic import (
    CREATION_DEFICIT,
    CREATION_GRACE_HOURS,
    MAX_ADMINS_PER_CLAN,
    MAX_MODS_PER_CLAN,
    TAG_MAX_LENGTH,
    TAG_MIN_LENGTH,
    is_creation_deficit_covered,
    next_channel_unlock_cost,
    next_channel_voice_hours_requirement,
    validate_guild_tag,
    voice_ticks_to_hours,
)
from core.repositories.guild_clan_repo import (
    REASON_GUILD_BOOST,
    ROLE_ADMIN,
    ROLE_CO_OWNER,
    ROLE_MEMBER,
    ROLE_MOD,
    ROLE_OWNER,
    guild_clan_repo,
)
from core.guild_clan_role_service import (
    clear_member_clan_presence,
    sync_member_clan_role,
)
from core.guild_clan_boost_logic import (
    BOOST_DURATION_HOURS,
    BOOST_MULTIPLIER,
    GUILD_BOOST_COST,
    INDIVIDUAL_BOOST_COST,
    extend_boost_expiry,
    is_boost_active,
)
from core.leveling_logic import (
    DAILY_COOLDOWN_SECONDS,
    DAILY_REWARD_COINS,
    WORK_COOLDOWN_SECONDS,
    WORK_REWARD_MAX,
    WORK_REWARD_MIN,
    is_eligible_for_voice_xp,
    period_key,
    seconds_until_next_claim,
    xp_for_level,
)
from core.premium import PremiumModule, registry

logger = logging.getLogger("iyokai.leveling")

MODULE_LEVELING = "leveling"

# Solo questi tipi di messaggio danno XP: quelli scritti da una persona.
TIPI_DI_MESSAGGIO_CON_XP = (discord.MessageType.default, discord.MessageType.reply)


# Limite di Discord per il motivo scritto nel registro di controllo.
LIMITE_MOTIVO = 512

# Chi può gestire la gilda: invitare, espellere, comprare canali e boost.
RUOLI_UFFICIALI = (ROLE_OWNER, ROLE_CO_OWNER, ROLE_ADMIN)

# LIM-18: lunghezza massima dei testi liberi e dei titoli degli embed.
MAX_NOME_CLAN = 64
MAX_NOME_OGGETTO = 80
MAX_DESCRIZIONE_OGGETTO = 200
MAX_PREMIO_GIVEAWAY = 200
MAX_NOME_CANALE = 100
LIMITE_TITOLO_EMBED = 256
LIMITE_RIGA_NEGOZIO = 380
RUOLI_PREMIO_PER_PAGINA = 20
MEMBRI_PER_PAGINA = 20


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

        SEC-4/SEC-17: l'assegnazione è automatica (self_service=True),
        quindi ogni ruolo viene ricontrollato con check_role_assignable
        prima di assegnarlo — il ruolo può aver preso permessi
        pericolosi dopo la configurazione del ruolo-premio.
        """
        ricompense = await level_reward_repo.get_rewards_up_to_level(guild.id, new_level)
        if not ricompense:
            return

        id_ruoli_posseduti = {ruolo.id for ruolo in member.roles}
        da_assegnare = []
        for r in ricompense:
            if r.role_id in id_ruoli_posseduti:
                continue
            ruolo = guild.get_role(r.role_id)
            if ruolo is None:
                continue
            if check_role_assignable(guild, ruolo, guild.me, self_service=True) is not None:
                continue
            da_assegnare.append(ruolo)
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

    class DropClaimView(BaseView):
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
            # BUG-17: nessun await tra controllo e assegnazione: è atomico.
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
        # I messaggi di sistema (boost, messaggio fissato, benvenuto
        # automatico) hanno un autore vero ma non li ha scritti lui.
        if message.type not in TIPI_DI_MESSAGGIO_CON_XP:
            return

        # SEC-10: un utente in blacklist non deve continuare a
        # guadagnare XP/coin scrivendo messaggi.
        if await blacklist_repo.is_user_blacklisted(message.author.id):
            return

        if not await db.is_module_active_for_guild(message.guild.id, MODULE_LEVELING):
            return

        clan = await guild_clan_repo.get_member_clan_in_guild(message.guild.id, message.author.id)
        if clan is not None and clan.officialized:
            # Lato TESTUALE del guadagno ×2 di gilda (SPEC.md
            # §15.14) — indipendente dall'XP personale sopra: stesso
            # cooldown del testo normale, nessuna coin, nessun boost
            # (scoped al solo vocale, Fase 54). Un fallimento qui non
            # deve mai impedire l'XP personale, quindi va PRIMA
            # dell'add_text_xp solo per ordine di lettura, non di
            # dipendenza — le due chiamate sono indipendenti.
            await guild_clan_repo.apply_text_tick(clan.id, message.author.id)

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
                # SEC-10: un utente in blacklist non deve continuare a
                # guadagnare XP vocale.
                if await blacklist_repo.is_user_blacklisted(member.id):
                    continue

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

        adesso = datetime.now(timezone.utc)
        riscosso = await leveling_repo.claim_daily(
            interaction.guild.id, interaction.user.id,
            DAILY_REWARD_COINS, DAILY_COOLDOWN_SECONDS, adesso,
        )
        if not riscosso:
            totali = await leveling_repo.get_totals(interaction.guild.id, interaction.user.id)
            attesa = seconds_until_next_claim(totali.last_daily_at, DAILY_COOLDOWN_SECONDS)
            await interaction.response.send_message(
                f"Hai già riscosso la ricompensa di oggi. Riprova tra {_format_seconds(attesa)}.",
                ephemeral=True,
            )
            return

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

        adesso = datetime.now(timezone.utc)
        guadagno = random.randint(WORK_REWARD_MIN, WORK_REWARD_MAX)
        riscosso = await leveling_repo.claim_work(
            interaction.guild.id, interaction.user.id,
            guadagno, WORK_COOLDOWN_SECONDS, adesso,
        )
        if not riscosso:
            totali = await leveling_repo.get_totals(interaction.guild.id, interaction.user.id)
            attesa = seconds_until_next_claim(totali.last_work_at, WORK_COOLDOWN_SECONDS)
            await interaction.response.send_message(
                f"Sei stanco, riposati un po'. Riprova tra {_format_seconds(attesa)}.",
                ephemeral=True,
            )
            return

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

        if not isinstance(interaction.user, discord.Member):
            return

        motivo_rifiuto = check_role_assignable(guild, role, interaction.user, self_service=True)
        if motivo_rifiuto is not None:
            await interaction.response.send_message(motivo_rifiuto, ephemeral=True)
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
        await invia_lista(
            interaction, "🏅 Ruoli-premio configurati", righe, discord.Color.gold(),
            ephemeral=True, per_pagina=RUOLI_PREMIO_PER_PAGINA,
        )


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
            nome = taglia(oggetto.name, MAX_NOME_OGGETTO)
            riga = f"`{oggetto.id}` **{nome}** — {oggetto.price} coin"
            if oggetto.role_id is not None:
                riga += f" (ruolo <@&{oggetto.role_id}>)"
            if oggetto.description:
                riga += f"\n> {taglia(oggetto.description, MAX_DESCRIZIONE_OGGETTO)}"
            righe.append(taglia(riga, LIMITE_RIGA_NEGOZIO))

        await invia_lista(interaction, "🛒 Shop", righe, discord.Color.green())

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

        # SEC-4/SEC-17: il ruolo si ricontrolla PRIMA di far spendere i
        # coin: può essere stato cancellato o aver preso permessi
        # pericolosi dopo che è stato messo nello shop.
        ruolo_shop = None
        if oggetto.role_id is not None:
            ruolo_shop = guild.get_role(oggetto.role_id)
            if ruolo_shop is None:
                await interaction.response.send_message(
                    "Questo oggetto non è più acquistabile: il suo ruolo non esiste più.",
                    ephemeral=True,
                )
                return
            motivo_rifiuto = check_role_assignable(guild, ruolo_shop, guild.me, self_service=True)
            if motivo_rifiuto is not None:
                await interaction.response.send_message(
                    f"Questo oggetto non è più acquistabile: {motivo_rifiuto}",
                    ephemeral=True,
                )
                return

        acquisto = await shop_repo.buy_item(guild.id, interaction.user.id, oggetto)
        if acquisto.esito == EsitoAcquisto.GIA_ACQUISTATO:
            await interaction.response.send_message(
                "Hai già acquistato questo oggetto.", ephemeral=True
            )
            return
        if acquisto.esito == EsitoAcquisto.SALDO_INSUFFICIENTE:
            await interaction.response.send_message(
                f"Non hai abbastanza coin — servono **{oggetto.price}**.", ephemeral=True
            )
            return

        nome = taglia(oggetto.name, 200)
        conferma = f"✅ Hai acquistato **{nome}** per {oggetto.price} coin!"
        if ruolo_shop is None:
            await interaction.response.send_message(conferma)
            return

        # Da qui si parla con Discord: prima il defer, poi il ruolo.
        await interaction.response.defer()
        try:
            await interaction.user.add_roles(
                ruolo_shop, reason=taglia(f"Acquisto shop: {oggetto.name}", LIMITE_MOTIVO)
            )
        except discord.HTTPException:
            # Il ruolo non è arrivato: l'acquisto si annulla e i coin
            # tornano indietro.
            await shop_repo.refund_purchase(
                acquisto.purchase_id, guild.id, interaction.user.id, oggetto.price
            )
            logger.warning(
                "Impossibile assegnare il ruolo shop %s a %s: acquisto rimborsato.",
                oggetto.role_id,
                interaction.user.id,
            )
            await interaction.followup.send(
                "Non sono riuscito a darti il ruolo: l'acquisto è annullato e i "
                f"**{oggetto.price}** coin ti sono stati restituiti.",
                ephemeral=True,
            )
            return

        await interaction.followup.send(conferma)

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
        name: app_commands.Range[str, 1, MAX_NOME_OGGETTO],
        price: app_commands.Range[int, 1, 1000000],
        role: discord.Role | None = None,
        description: app_commands.Range[str, 1, MAX_DESCRIZIONE_OGGETTO] | None = None,
    ) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return

        if role is not None and isinstance(interaction.user, discord.Member):
            motivo_rifiuto = check_role_assignable(guild, role, interaction.user, self_service=True)
            if motivo_rifiuto is not None:
                await interaction.response.send_message(motivo_rifiuto, ephemeral=True)
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

    @app_commands.command(
        name="assegna-lobby",
        description="[Admin] Premio partecipazione: assegna coin a chi è in vocale ORA, dalla cassa del server.",
    )
    @app_commands.describe(importo="Quante coin assegnare a CIASCUNO dei presenti in vocale")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def assegna_lobby(
        self, interaction: discord.Interaction, importo: app_commands.Range[int, 1, 1_000_000]
    ) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return

        # LIM-25: con molte persone il lavoro supera i 3 secondi.
        await interaction.response.defer()

        # I presenti si leggono una volta sola, tutti insieme. SEC-21:
        # chi è in blacklist non riceve il premio e non viene contato
        # nel costo per la cassa.
        in_vocale = {
            membro.id
            for canale in guild.voice_channels
            for membro in canale.members
            if not membro.bot
        }
        presenti = [
            membro_id
            for membro_id in sorted(in_vocale)
            if not await blacklist_repo.is_user_blacklisted(membro_id)
        ]
        if not presenti:
            await interaction.followup.send(
                "Nessuno è in vocale in questo momento — nessuna coin assegnata.", ephemeral=True
            )
            return

        # LC-1: addebito e accrediti in una sola transazione.
        costo_totale = importo * len(presenti)
        riuscito = await guild_chest_repo.pay_members(
            guild.id, presenti, importo, reason=REASON_EVENT_LOBBY_PRIZE
        )
        if not riuscito:
            saldo = await guild_chest_repo.get_balance(guild.id)
            await interaction.followup.send(
                f"La cassa non basta — servono **{costo_totale}** coin per **{len(presenti)}** "
                f"persone in vocale (ne avete **{saldo}**).",
                ephemeral=True,
            )
            return

        await interaction.followup.send(
            f"✅ Assegnate **{importo}** coin a **{len(presenti)}** persone in vocale "
            f"(**{costo_totale}** coin totali dalla cassa)."
        )

    @app_commands.command(
        name="assegna-winner",
        description="[Admin] Premio vincitore: assegna coin a un membro, dalla cassa del server.",
    )
    @app_commands.describe(membro="Il membro da premiare", importo="Quante coin assegnare")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def assegna_winner(
        self,
        interaction: discord.Interaction,
        membro: discord.Member,
        importo: app_commands.Range[int, 1, 1_000_000],
    ) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return

        # SEC-21: nessun premio a chi è in blacklist.
        if await blacklist_repo.is_user_blacklisted(membro.id):
            await interaction.response.send_message(
                "Questo utente non può ricevere premi.", ephemeral=True
            )
            return

        # Addebito e accredito nella stessa transazione, come /assegna-lobby.
        riuscito = await guild_chest_repo.pay_members(
            guild.id, [membro.id], importo, reason=REASON_EVENT_WINNER_PRIZE
        )
        if not riuscito:
            saldo = await guild_chest_repo.get_balance(guild.id)
            await interaction.response.send_message(
                f"La cassa non basta — servono **{importo}** coin (ne avete **{saldo}**).",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            f"🏆 {membro.mention} ha vinto **{importo}** coin dalla cassa del server!"
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
    async def clan_crea(
        self,
        interaction: discord.Interaction,
        tag: app_commands.Range[str, TAG_MIN_LENGTH, TAG_MAX_LENGTH],
        name: app_commands.Range[str, 1, MAX_NOME_CLAN],
    ) -> None:
        guild = interaction.guild
        if guild is None or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return

        # LIM-25: più chiamate a Discord, quindi defer() per primo.
        await interaction.response.defer()

        valido, motivo = validate_guild_tag(tag)
        if not valido:
            await interaction.followup.send(motivo, ephemeral=True)
            return

        if await guild_clan_repo.get_member_clan_in_guild(guild.id, interaction.user.id):
            await interaction.followup.send(
                "Fai già parte di una gilda in questo server — lasciala prima di crearne una nuova.",
                ephemeral=True,
            )
            return

        if await guild_clan_repo.is_tag_taken(guild.id, tag):
            await interaction.followup.send(
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
                reason=taglia(f"Creazione gilda '{tag}' da {interaction.user}", LIMITE_MOTIVO),
            )
        except discord.Forbidden:
            await interaction.followup.send(
                "Non ho i permessi per creare una categoria in questo server.", ephemeral=True
            )
            return
        except discord.HTTPException:
            await interaction.followup.send(
                "Creazione della categoria fallita — riprova più tardi.", ephemeral=True
            )
            return

        scadenza = datetime.now(timezone.utc) + timedelta(hours=CREATION_GRACE_HOURS)
        clan_id = await guild_clan_repo.create_clan(
            guild.id, tag=tag, name=name, owner_id=interaction.user.id,
            officialize_deadline=scadenza,
        )
        if clan_id is None:
            # Un'altra creazione con lo stesso tag è arrivata un attimo
            # prima: la categoria appena creata non serve più.
            try:
                await categoria.delete(reason=f"Gilda '{tag}' non creata: tag già usato")
            except discord.HTTPException:
                logger.warning("Impossibile eliminare la categoria %s rimasta senza gilda.", categoria.id)
            await interaction.followup.send(
                f"Il tag `{tag}` è già usato da un'altra gilda in questo server.",
                ephemeral=True,
            )
            return
        await guild_clan_repo.set_category_id(clan_id, categoria.id)
        await sync_member_clan_role(guild, categoria, interaction.user, ROLE_OWNER)

        await interaction.followup.send(
            f"✅ Gilda **{name}** (`{tag}`) creata! Per ufficializzarla servono "
            f"**{CREATION_DEFICIT}** coin in tesoreria entro **{CREATION_GRACE_HOURS} ore** "
            f"(`/clan tesoreria dona`) — altrimenti verrà eliminata automaticamente."
        )

    @clan_group.command(name="info", description="Mostra le informazioni di una gilda.")
    @app_commands.describe(tag="Tag della gilda (facoltativo: la tua, se non specificato)")
    async def clan_info(
        self,
        interaction: discord.Interaction,
        tag: app_commands.Range[str, TAG_MIN_LENGTH, TAG_MAX_LENGTH] | None = None,
    ) -> None:
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
            title=taglia(f"🛡️ [{clan.tag}] {clan.name}", LIMITE_TITOLO_EMBED),
            color=discord.Color.blurple(),
        )
        embed.add_field(name="Stato", value=stato, inline=False)
        embed.add_field(name="Capo Clan", value=f"<@{clan.owner_id}>", inline=True)
        if clan.co_owner_id is not None:
            embed.add_field(name="Co-Owner", value=f"<@{clan.co_owner_id}>", inline=True)
        embed.add_field(name="Membri", value=f"{n_membri}/{clan.max_members}", inline=True)
        embed.add_field(name="Tesoreria", value=f"{clan.treasury_balance} coin", inline=True)
        embed.add_field(name="XP totale", value=str(clan.total_xp), inline=True)
        ore_accumulate = voice_ticks_to_hours(clan.total_voice_ticks)
        ore_richieste = next_channel_voice_hours_requirement(clan.channels_unlocked)
        prossimo_costo = next_channel_unlock_cost(clan.channels_unlocked)
        if prossimo_costo is None:
            valore_canali = f"{clan.channels_unlocked} (massimo raggiunto)"
        else:
            valore_canali = (
                f"{clan.channels_unlocked} — prossimo: **{prossimo_costo}** coin + "
                f"**{ore_richieste}**h vocali (ne avete {ore_accumulate})"
            )
        embed.add_field(name="Canali sbloccati", value=valore_canali, inline=False)

        if is_boost_active(clan.guild_boost_expires_at, datetime.now(timezone.utc)):
            embed.add_field(
                name="Boost di gilda",
                value=f"✨ Attivo ×{BOOST_MULTIPLIER} fino a <t:{int(clan.guild_boost_expires_at.timestamp())}:R>",
                inline=False,
            )

        await interaction.response.send_message(embed=embed)

    @clan_group.command(name="membri", description="Mostra i membri di una gilda.")
    @app_commands.describe(tag="Tag della gilda (facoltativo: la tua, se non specificato)")
    async def clan_membri(
        self,
        interaction: discord.Interaction,
        tag: app_commands.Range[str, TAG_MIN_LENGTH, TAG_MAX_LENGTH] | None = None,
    ) -> None:
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
        righe = [f"<@{m.user_id}> — {m.role}" for m in membri] or ["Nessun membro."]
        await invia_lista(
            interaction, f"Membri di [{clan.tag}] {clan.name}", righe,
            discord.Color.blurple(), per_pagina=MEMBRI_PER_PAGINA,
        )

    @clan_group.command(
        name="classifica", description="Classifica delle gilde per XP (mensile o totale)."
    )
    @app_commands.describe(period="Questo mese o di sempre")
    @app_commands.choices(
        period=[
            app_commands.Choice(name="Questo mese", value="month"),
            app_commands.Choice(name="Di sempre", value="alltime"),
        ]
    )
    async def clan_classifica(
        self,
        interaction: discord.Interaction,
        period: app_commands.Choice[str] | None = None,
    ) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return

        # Default: totale all-time (comportamento storico del
        # comando, invariato per chi lo usa senza specificare nulla).
        mensile = period is not None and period.value == "month"

        if mensile:
            voci = await guild_clan_repo.get_monthly_clan_leaderboard(guild.id)
            if not voci:
                await interaction.response.send_message(
                    "Nessuna gilda ha guadagnato XP questo mese in questo server.",
                    ephemeral=True,
                )
                return
            righe = [
                f"**{i+1}.** [{c.tag}] {taglia(c.name, MAX_NOME_CLAN)} — {xp} XP"
                for i, (c, xp) in enumerate(voci)
            ]
            titolo = "🏆 Classifica Gilde — questo mese"
        else:
            classifica = await guild_clan_repo.get_clan_leaderboard(guild.id)
            if not classifica:
                await interaction.response.send_message(
                    "Nessuna gilda in questo server ancora.", ephemeral=True
                )
                return
            righe = [
                f"**{i+1}.** [{c.tag}] {taglia(c.name, MAX_NOME_CLAN)} — {c.total_xp} XP"
                for i, c in enumerate(classifica)
            ]
            titolo = "🏆 Classifica Gilde — di sempre"

        embed = discord.Embed(
            title=titolo, description="\n".join(righe), color=discord.Color.gold()
        )
        await interaction.response.send_message(embed=embed)

    clan_bacheca_group = app_commands.Group(
        name="bacheca",
        description="[Admin] Annuncio automatico della top 3 gilde a fine mese.",
        parent=clan_group,
    )

    @clan_bacheca_group.command(
        name="set", description="[Admin] Imposta il canale dove annunciare la top 3 gilde del mese."
    )
    @app_commands.describe(channel="Canale dell'annuncio (la 'bacheca clan')")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def clan_bacheca_set(
        self, interaction: discord.Interaction, channel: discord.TextChannel
    ) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return

        await clan_leaderboard_config_repo.set_channel(
            guild.id, channel.id, already_covered_period=clan_previous_period_key()
        )
        await interaction.response.send_message(
            f"✅ La top 3 gilde del mese verrà annunciata in {channel.mention} "
            f"all'inizio di ogni mese (il primo annuncio al prossimo cambio mese).",
            ephemeral=True,
        )

    @clan_bacheca_group.command(
        name="disable", description="[Admin] Disattiva l'annuncio automatico della top 3 gilde."
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def clan_bacheca_disable(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None:
            return

        if await clan_leaderboard_config_repo.disable(guild.id):
            await interaction.response.send_message(
                "Annuncio della top 3 gilde disattivato.", ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "L'annuncio della top 3 gilde non era attivo su questo server.", ephemeral=True
            )

    @clan_group.command(name="sciogli", description="[Capo Clan] Sciogli la tua gilda.")
    async def clan_sciogli(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return

        # LIM-25: più chiamate a Discord, quindi defer() per primo.
        await interaction.response.defer()

        clan = await guild_clan_repo.get_member_clan_in_guild(guild.id, interaction.user.id)
        if clan is None:
            await interaction.followup.send(
                "Non fai parte di nessuna gilda in questo server.", ephemeral=True
            )
            return
        if clan.owner_id != interaction.user.id:
            await interaction.followup.send(
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
        await interaction.followup.send(f"La gilda **{clan.name}** è stata sciolta.")

    @clan_group.command(name="invita", description="[Capo/Admin Clan] Invita un membro nella tua gilda.")
    @app_commands.describe(membro="Il membro da invitare nella tua gilda")
    async def clan_invita(self, interaction: discord.Interaction, membro: discord.Member) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return

        # LIM-25: più chiamate a Discord, quindi defer() per primo.
        await interaction.response.defer()

        clan = await guild_clan_repo.get_member_clan_in_guild(guild.id, interaction.user.id)
        if clan is None:
            await interaction.followup.send(
                "Non fai parte di nessuna gilda in questo server.", ephemeral=True
            )
            return

        chi_invita = await guild_clan_repo.get_member(clan.id, interaction.user.id)
        if chi_invita is None or chi_invita.role not in RUOLI_UFFICIALI:
            await interaction.followup.send(
                "Solo il Capo Clan, il Co-Owner o un Admin Clan possono invitare nuovi membri.", ephemeral=True
            )
            return

        if await guild_clan_repo.get_member_clan_in_guild(guild.id, membro.id) is not None:
            await interaction.followup.send(
                f"{membro.mention} fa già parte di una gilda in questo server.", ephemeral=True
            )
            return

        if await guild_clan_repo.count_members(clan.id) >= clan.max_members:
            await interaction.followup.send(
                f"La gilda ha già raggiunto il limite di **{clan.max_members}** membri.", ephemeral=True
            )
            return

        await guild_clan_repo.add_member(clan.id, membro.id, role=ROLE_MEMBER)

        categoria = guild.get_channel(clan.category_id) if clan.category_id is not None else None
        await sync_member_clan_role(guild, categoria, membro, ROLE_MEMBER)

        await interaction.followup.send(
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

        # LIM-25: più chiamate a Discord, quindi defer() per primo.
        await interaction.response.defer()

        clan = await guild_clan_repo.get_member_clan_in_guild(guild.id, interaction.user.id)
        if clan is None:
            await interaction.followup.send(
                "Non fai parte di nessuna gilda in questo server.", ephemeral=True
            )
            return

        chi_espelle = await guild_clan_repo.get_member(clan.id, interaction.user.id)
        if chi_espelle is None or chi_espelle.role not in RUOLI_UFFICIALI:
            await interaction.followup.send(
                "Solo il Capo Clan, il Co-Owner o un Admin Clan possono espellere membri.", ephemeral=True
            )
            return

        target = await guild_clan_repo.get_member(clan.id, membro.id)
        if target is None:
            await interaction.followup.send(
                f"{membro.mention} non fa parte della tua gilda.", ephemeral=True
            )
            return

        if membro.id == clan.owner_id:
            await interaction.followup.send(
                "Il Capo Clan non può essere espulso — usa `/clan sciogli` per sciogliere la gilda.",
                ephemeral=True,
            )
            return

        if chi_espelle.role == ROLE_ADMIN and target.role in (ROLE_ADMIN, ROLE_CO_OWNER):
            await interaction.followup.send(
                "Un Admin Clan non può espellere un altro Admin Clan né il Co-Owner — "
                "serve il Capo Clan.",
                ephemeral=True,
            )
            return

        await guild_clan_repo.remove_member(clan.id, membro.id)

        categoria = guild.get_channel(clan.category_id) if clan.category_id is not None else None
        await clear_member_clan_presence(guild, categoria, membro)

        await interaction.followup.send(
            f"✅ {membro.mention} è stato espulso da **{clan.name}**."
        )

    @clan_group.command(name="promuovi", description="[Capo Clan] Cambia il ruolo di un membro della tua gilda.")
    @app_commands.describe(membro="Il membro a cui cambiare ruolo", ruolo="Il nuovo ruolo da assegnare")
    async def clan_promuovi(
        self,
        interaction: discord.Interaction,
        membro: discord.Member,
        ruolo: Literal["co_owner", "admin", "mod", "member"],
    ) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return

        # LIM-25: più chiamate a Discord, quindi defer() per primo.
        await interaction.response.defer()

        clan = await guild_clan_repo.get_member_clan_in_guild(guild.id, interaction.user.id)
        if clan is None:
            await interaction.followup.send(
                "Non fai parte di nessuna gilda in questo server.", ephemeral=True
            )
            return

        if clan.owner_id != interaction.user.id:
            await interaction.followup.send(
                "Solo il Capo Clan può cambiare il ruolo dei membri.", ephemeral=True
            )
            return

        if membro.id == clan.owner_id:
            await interaction.followup.send(
                "Il Capo Clan non può cambiare il proprio ruolo.", ephemeral=True
            )
            return

        target = await guild_clan_repo.get_member(clan.id, membro.id)
        if target is None:
            await interaction.followup.send(
                f"{membro.mention} non fa parte della tua gilda.", ephemeral=True
            )
            return

        if ruolo == ROLE_ADMIN and target.role != ROLE_ADMIN:
            if await guild_clan_repo.count_members_with_role(clan.id, ROLE_ADMIN) >= MAX_ADMINS_PER_CLAN:
                await interaction.followup.send(
                    f"La gilda ha già raggiunto il limite di **{MAX_ADMINS_PER_CLAN}** Admin Clan.",
                    ephemeral=True,
                )
                return
        elif ruolo == ROLE_MOD and target.role != ROLE_MOD:
            if await guild_clan_repo.count_members_with_role(clan.id, ROLE_MOD) >= MAX_MODS_PER_CLAN:
                await interaction.followup.send(
                    f"La gilda ha già raggiunto il limite di **{MAX_MODS_PER_CLAN}** Mod Clan.",
                    ephemeral=True,
                )
                return

        if not await guild_clan_repo.set_member_role(clan.id, membro.id, ruolo):
            await interaction.followup.send(
                "La gilda ha già un Co-Owner: riportalo prima a un altro ruolo.",
                ephemeral=True,
            )
            return

        categoria = guild.get_channel(clan.category_id) if clan.category_id is not None else None
        await sync_member_clan_role(guild, categoria, membro, ruolo)

        await interaction.followup.send(
            f"✅ {membro.mention} è ora **{ruolo}** in **{clan.name}**."
        )

    @clan_group.command(
        name="compra-canale",
        description="[Capo/Admin Clan] Sblocca un nuovo canale extra per la tua gilda.",
    )
    @app_commands.describe(
        tipo="Tipo di canale da creare",
        nome="Nome del canale (facoltativo: generato dal tag della gilda se non specificato)",
    )
    async def clan_compra_canale(
        self,
        interaction: discord.Interaction,
        tipo: Literal["testuale", "vocale", "forum"],
        nome: app_commands.Range[str, 1, MAX_NOME_CANALE] | None = None,
    ) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return

        # LIM-25: più chiamate a Discord, quindi defer() per primo.
        await interaction.response.defer()

        clan = await guild_clan_repo.get_member_clan_in_guild(guild.id, interaction.user.id)
        if clan is None:
            await interaction.followup.send(
                "Non fai parte di nessuna gilda in questo server.", ephemeral=True
            )
            return

        chi_acquista = await guild_clan_repo.get_member(clan.id, interaction.user.id)
        if chi_acquista is None or chi_acquista.role not in RUOLI_UFFICIALI:
            await interaction.followup.send(
                "Solo il Capo Clan, il Co-Owner o un Admin Clan possono acquistare nuovi canali.", ephemeral=True
            )
            return

        costo = next_channel_unlock_cost(clan.channels_unlocked)
        if costo is None:
            await interaction.followup.send(
                "La tua gilda ha già sbloccato tutti i canali extra disponibili.", ephemeral=True
            )
            return

        ore_richieste = next_channel_voice_hours_requirement(clan.channels_unlocked)
        ore_accumulate = voice_ticks_to_hours(clan.total_voice_ticks)
        if ore_accumulate < ore_richieste:
            await interaction.followup.send(
                f"Servono **{ore_richieste}** ore vocali accumulate dalla gilda per il prossimo "
                f"canale (ne avete accumulate **{ore_accumulate}**).",
                ephemeral=True,
            )
            return

        if clan.treasury_balance < costo:
            await interaction.followup.send(
                f"La tesoreria della gilda non basta — servono **{costo}** coin "
                f"(ne avete **{clan.treasury_balance}**).",
                ephemeral=True,
            )
            return

        categoria = guild.get_channel(clan.category_id) if clan.category_id is not None else None
        if categoria is None:
            await interaction.followup.send(
                "La categoria della tua gilda non esiste più su Discord — contatta lo staff.",
                ephemeral=True,
            )
            return

        # Prima l'addebito (una sola UPDATE con i controlli dentro),
        # poi il canale su Discord. Se un altro acquisto è arrivato un
        # attimo prima, questo non passa.
        if not await guild_clan_repo.unlock_channel(clan.id, clan.channels_unlocked, costo):
            await interaction.followup.send(
                "L'acquisto non è andato a buon fine: la tesoreria o i canali sbloccati sono "
                "cambiati nel frattempo. Riprova.",
                ephemeral=True,
            )
            return

        nome_canale = (nome or f"{clan.tag.lower()}-canale-{clan.channels_unlocked + 1}")[:100]
        motivo = taglia(f"Canale extra sbloccato per la gilda '{clan.tag}'", LIMITE_MOTIVO)
        try:
            if tipo == "testuale":
                await guild.create_text_channel(nome_canale, category=categoria, reason=motivo)
            elif tipo == "vocale":
                await guild.create_voice_channel(nome_canale, category=categoria, reason=motivo)
            else:
                await guild.create_forum(nome_canale, category=categoria, reason=motivo)
        except discord.HTTPException as errore:
            # Il canale non è nato: la spesa si annulla.
            await guild_clan_repo.refund_channel_unlock(clan.id, costo)
            if isinstance(errore, discord.Forbidden):
                testo = "Non ho i permessi per creare un canale in questa categoria."
            else:
                testo = "Creazione del canale fallita — riprova più tardi."
            await interaction.followup.send(
                f"{testo} I **{costo}** coin sono tornati in tesoreria.", ephemeral=True
            )
            return

        await interaction.followup.send(
            f"✅ Nuovo canale **{tipo}** sbloccato per **{clan.name}** — spesi **{costo}** coin "
            f"dalla tesoreria."
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
        # La gilda diventa ufficiale dentro la donazione stessa (repository).
        if not clan.officialized and is_creation_deficit_covered(nuovo_saldo):
            messaggio += "\n🎉 Il deficit di creazione è coperto: la gilda è ora **ufficializzata**!"

        await interaction.response.send_message(messaggio)

    @clan_tesoreria_group.command(
        name="trasferisci",
        description="[Capo Clan] Trasferisci coin dalla tesoreria a un'altra TUA gilda (anche su un altro server).",
    )
    @app_commands.describe(
        tag_destinazione="Tag dell'altra gilda di cui sei Capo Clan (anche su un server diverso)",
        importo="Quante coin trasferire dalla tesoreria di questa gilda",
    )
    async def clan_tesoreria_trasferisci(
        self,
        interaction: discord.Interaction,
        tag_destinazione: app_commands.Range[str, TAG_MIN_LENGTH, TAG_MAX_LENGTH],
        importo: app_commands.Range[int, 1, 1_000_000_000],
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
                "Solo il Capo Clan può trasferire la tesoreria verso un'altra tua gilda.",
                ephemeral=True,
            )
            return

        # L'UNICA condizione per un trasferimento tra tesorerie è lo
        # stesso owner — MAI lo stesso server: un Capo Clan può avere
        # una seconda gilda su un altro server con lo stesso bot, e
        # senza questo le coin di quella gilda resterebbero bloccate
        # per sempre nel server in cui sono state guadagnate.
        proprie_gilde = await guild_clan_repo.list_clans_owned_by(interaction.user.id)
        candidate = [c for c in proprie_gilde if c.tag == tag_destinazione and c.id != clan.id]

        if not candidate:
            await interaction.response.send_message(
                f"Non sei Capo Clan di nessun'altra gilda con tag `{tag_destinazione}` "
                f"(su nessun server).",
                ephemeral=True,
            )
            return
        if len(candidate) > 1:
            await interaction.response.send_message(
                f"Hai più di una gilda con tag `{tag_destinazione}` (su server diversi) — "
                f"rinomina il tag di una delle due per distinguerle prima di trasferire.",
                ephemeral=True,
            )
            return

        destinazione = candidate[0]
        riuscito = await guild_clan_repo.transfer_between_treasuries(clan.id, destinazione.id, importo)
        if not riuscito:
            await interaction.response.send_message(
                f"La tesoreria di **{clan.name}** non basta — servono **{importo}** coin "
                f"(ne avete **{clan.treasury_balance}**).",
                ephemeral=True,
            )
            return

        nota_cross_server = (
            " (su un altro server)" if destinazione.guild_id != guild.id else ""
        )
        messaggio = (
            f"✅ Trasferite **{importo}** coin dalla tesoreria di **{clan.name}** a "
            f"**{destinazione.name}**{nota_cross_server}."
        )
        # BUG-15: il trasferimento può aver coperto il debito di creazione.
        aggiornata = await guild_clan_repo.get_clan_by_tag(
            destinazione.guild_id, destinazione.tag
        )
        if aggiornata is not None and aggiornata.officialized and not destinazione.officialized:
            messaggio += (
                f"\n🎉 Il deficit di creazione è coperto: **{destinazione.name}** è ora "
                "**ufficializzata**!"
            )
        await interaction.response.send_message(messaggio)

    clan_boost_group = app_commands.Group(
        name="boost", description="Boost XP/coin del Sistema Gilde/Clan.", parent=clan_group
    )

    @clan_boost_group.command(
        name="individuale",
        description=f"Acquista un boost personale ×{BOOST_MULTIPLIER} per {BOOST_DURATION_HOURS}h sul tuo tick vocale di gilda.",
    )
    async def clan_boost_individuale(self, interaction: discord.Interaction) -> None:
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

        riuscito = await leveling_repo.spend_coins(guild.id, interaction.user.id, INDIVIDUAL_BOOST_COST)
        if not riuscito:
            await interaction.response.send_message(
                f"Non hai abbastanza coin personali — servono **{INDIVIDUAL_BOOST_COST}**.",
                ephemeral=True,
            )
            return

        membro = await guild_clan_repo.get_member(clan.id, interaction.user.id)
        adesso = datetime.now(timezone.utc)
        nuova_scadenza = extend_boost_expiry(
            membro.boost_expires_at if membro is not None else None, adesso
        )
        await guild_clan_repo.set_member_boost_expiry(clan.id, interaction.user.id, nuova_scadenza)

        await interaction.response.send_message(
            f"✅ Boost personale ×{BOOST_MULTIPLIER} attivo sul tuo tick vocale in **{clan.name}** "
            f"fino a <t:{int(nuova_scadenza.timestamp())}:f>."
        )

    @clan_boost_group.command(
        name="gilda",
        description=f"[Capo/Admin Clan] Acquista un boost ×{BOOST_MULTIPLIER} per {BOOST_DURATION_HOURS}h per TUTTI i membri, dalla tesoreria.",
    )
    async def clan_boost_gilda(self, interaction: discord.Interaction) -> None:
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

        chi_acquista = await guild_clan_repo.get_member(clan.id, interaction.user.id)
        if chi_acquista is None or chi_acquista.role not in RUOLI_UFFICIALI:
            await interaction.response.send_message(
                "Solo il Capo Clan, il Co-Owner o un Admin Clan possono acquistare il boost di gilda.",
                ephemeral=True,
            )
            return

        riuscito = await guild_clan_repo.spend_from_treasury(
            clan.id, GUILD_BOOST_COST, reason=REASON_GUILD_BOOST
        )
        if not riuscito:
            await interaction.response.send_message(
                f"La tesoreria della gilda non basta — servono **{GUILD_BOOST_COST}** coin "
                f"(ne avete **{clan.treasury_balance}**).",
                ephemeral=True,
            )
            return

        adesso = datetime.now(timezone.utc)
        nuova_scadenza = extend_boost_expiry(clan.guild_boost_expires_at, adesso)
        await guild_clan_repo.set_guild_boost_expiry(clan.id, nuova_scadenza)

        await interaction.response.send_message(
            f"✅ Boost di gilda ×{BOOST_MULTIPLIER} attivo per TUTTI i membri di **{clan.name}** "
            f"fino a <t:{int(nuova_scadenza.timestamp())}:f>."
        )

    # ================================================================
    # Giveaway (SPEC.md §15.5, con requisiti di ruolo/livello)
    # ================================================================
    class GiveawayEnterView(BaseView):
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
        prize: app_commands.Range[str, 1, MAX_PREMIO_GIVEAWAY],
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
            title=taglia(f"🎉 Giveaway: {prize}", LIMITE_TITOLO_EMBED),
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
            category="leveling",
            description="XP, livelli, daily/work/pay, classifiche mensili e all-time.",
            premium_capable=False,
        )
    )
    await bot.add_cog(LevelingCog(bot))
