"""
cogs/security/anti_nuke.py
==============================
Anti-Nuke (SPEC.md §7.2): rilevamento di azioni distruttive di massa
(cancellazione canali/ruoli, webhook, emoji/sticker, mass ban/kick)
ed intervento automatico sull'autore, più recovery best-effort e
alert allo staff. Modulo CANDIDATO PREMIUM, come Anti-Raid.

L'autore di un evento non è mai nel payload dell'evento gateway
stesso (Discord non lo include) — va sempre risolto via audit log
(`guild.audit_logs`), stesso approccio già usato in
`cogs/security/spam_trap.py` per il cleanup di webhook/inviti.
Il registro si legge solo dove l'anti-nuke è attivo, e si rilegge se
la voce non è ancora arrivata.

Recovery: `on_guild_channel_delete`/`on_guild_role_delete` ricevono
l'oggetto come l'ultima volta che era nella cache del client, PRIMA
della rimozione — permette di ricreare canale/ruolo con lo stesso
nome/permessi/posizione senza dover mantenere uno snapshot separato.
I canali vengono ricreati dello stesso tipo (testuale, annunci,
vocale, palco, categoria, forum).

Funzioni coperte: SPEC §7.2
"""

# DA FARE (issue #59, fase F1): correzioni aperte per questo file in
#   revisione/02-piano/MODIFICHE_ESISTENTE.md §3 (Sicurezza (anti-raid,
#   anti-nuke, spam-trap, ban globale)).

from __future__ import annotations

import asyncio
import logging

import discord
from discord import app_commands
from discord.ext import commands

from core.bounded_cache import BoundedCache
from core.database import db
from core.premium import PremiumModule, registry, requires_module
from core.repositories.security_repo import SecuritySettings, security_repo
from core.security_access import premium_sbloccato
from core.security_logic import (
    AntiNukeConfig,
    NUKE_CATEGORY_BAN_KICK,
    NUKE_CATEGORY_CHANNEL,
    NUKE_CATEGORY_EMOJI,
    NUKE_CATEGORY_ROLE,
    NUKE_CATEGORY_WEBHOOK,
    category_max_count,
    category_window_seconds,
    is_nuke_violation,
)
from core.security_rate_tracker import security_rate_tracker
from cogs.moderation._shared import ensure_module_enabled, try_dm

logger = logging.getLogger("iyokai.anti_nuke")

MODULE_ANTI_NUKE = "anti_nuke"

# Finestra di ricerca nell'audit log: l'evento gateway e la riga di
# audit log corrispondente arrivano quasi sempre entro pochi secondi
# l'uno dall'altro, ma non sono garantiti nello stesso istante.
_AUDIT_LOG_LOOKBACK_SECONDS = 10

# Secondi di attesa prima di ogni lettura del registro di controllo:
# subito, poi altre due volte. Per le uscite dal server (quasi sempre
# volontarie, senza voce nel registro) basta una sola rilettura.
ATTESE_REGISTRO = (0, 1, 1)
ATTESE_REGISTRO_USCITA = (0, 1.5)

# Lunghezza massima di un motivo nel registro di controllo di Discord.
MAX_MOTIVO = 512

MOTIVO_RECOVERY = "Anti-Nuke: recovery automatico dopo cancellazione di massa"

# Quanti membri si rimettono a un ruolo ricreato (Discord limita le
# richieste: oltre il tetto si lascia il resto allo staff) e quante
# cancellazioni si tengono da parte per autore.
MAX_MEMBRI_RIPRISTINO = 500
MAX_IN_ATTESA = 100

# Dal 16/11/2026 un canale che il bot non può vedere arriva con questo
# nome finto (LIMITI.md, Parte 2).
NOME_CANALE_NASCOSTO = "___hidden___"


def _replace(settings: SecuritySettings, **overrides) -> SecuritySettings:
    dati = {
        "guild_id": settings.guild_id,
        "anti_raid": settings.anti_raid,
        "anti_nuke": settings.anti_nuke,
        "quarantine_role_id": settings.quarantine_role_id,
        "alert_channel_id": settings.alert_channel_id,
    }
    anti_nuke_fields = set(AntiNukeConfig.__dataclass_fields__.keys())
    anti_nuke_overrides = {k: v for k, v in overrides.items() if k in anti_nuke_fields}
    altri_overrides = {k: v for k, v in overrides.items() if k not in anti_nuke_fields}

    if anti_nuke_overrides:
        dati["anti_nuke"] = AntiNukeConfig(
            **{**{f: getattr(settings.anti_nuke, f) for f in anti_nuke_fields}, **anti_nuke_overrides}
        )
    dati.update(altri_overrides)
    return SecuritySettings(**dati)


async def _aspetta(secondi: float) -> None:
    await asyncio.sleep(secondi)


async def _resolve_actor(
    guild: discord.Guild,
    action: discord.AuditLogAction,
    target_id: int | None = None,
    attese: tuple[float, ...] = ATTESE_REGISTRO,
) -> int | None:
    """
    Cerca nel registro di controllo chi ha fatto questa azione
    (se `target_id` è dato, solo la voce che riguarda quell'oggetto).
    Il registro arriva spesso un attimo dopo l'evento: se la voce non
    c'è ancora si riprova, aspettando ogni volta i secondi di `attese`.
    None se non si trova o se Discord non lascia leggere il registro —
    mai un'eccezione che blocchi l'evento.
    """
    now = discord.utils.utcnow()
    for attesa in attese:
        if attesa:
            await _aspetta(attesa)
        try:
            async for entry in guild.audit_logs(action=action, limit=10):
                if (now - entry.created_at).total_seconds() > _AUDIT_LOG_LOOKBACK_SECONDS:
                    break
                if target_id is not None and getattr(entry.target, "id", None) != target_id:
                    continue
                return entry.user_id
        except discord.HTTPException:
            return None
    return None


async def _punish_actor(guild: discord.Guild, actor_id: int, config: AntiNukeConfig, reason: str) -> str:
    """Restituisce una descrizione di cosa è stato fatto, per il log/alert."""
    if guild.owner_id == actor_id:
        return "nessuna azione: l'autore è il proprietario del server"

    member = guild.get_member(actor_id)
    if member is None:
        return "nessuna azione: l'autore non è (più) un membro del server"

    reason = reason[:MAX_MOTIVO]

    if config.punish_action == "ban":
        try:
            await member.ban(reason=reason, delete_message_seconds=0)
            return f"{member} bannato"
        except discord.HTTPException:
            return f"tentativo di ban di {member} fallito (permessi insufficienti?)"

    if member.bot:
        # Il ruolo di un bot è gestito da Discord e non si può
        # togliere: un bot che fa danni va tolto dal server.
        try:
            await member.kick(reason=reason)
            return f"bot {member} espulso"
        except discord.HTTPException:
            return f"tentativo di espellere il bot {member} fallito (permessi insufficienti?)"

    # I ruoli gestiti da Discord (es. Server Booster) non si possono
    # togliere: chiederlo farebbe fallire tutta la modifica.
    ruoli_gestiti = [ruolo for ruolo in member.roles if ruolo.managed]
    try:
        await member.edit(roles=ruoli_gestiti, reason=reason)
        return f"tutti i ruoli rimossi da {member}"
    except discord.HTTPException:
        return f"tentativo di rimuovere i ruoli di {member} fallito (permessi insufficienti?)"


async def _alert_staff(guild: discord.Guild, settings: SecuritySettings, embed: discord.Embed) -> None:
    if guild.owner is not None:
        await try_dm(guild.owner, embed)
    if settings.alert_channel_id is not None:
        canale = guild.get_channel(settings.alert_channel_id)
        if isinstance(canale, discord.TextChannel):
            try:
                await canale.send(embed=embed)
            except discord.HTTPException:
                pass


class AntiNukeCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        # Categoria cancellata (ID vecchio) -> categoria ricreata.
        self._categorie_ricreate: BoundedCache[int, discord.CategoryChannel] = BoundedCache(
            max_size=500
        )
        # (server, autore) -> oggetti cancellati non ancora recuperati
        # perché l'autore era ancora sotto soglia.
        self._in_attesa: BoundedCache[tuple[int, int], list[object]] = BoundedCache(max_size=500)

    anti_nuke_group = app_commands.Group(
        name="anti-nuke", description="Configura la protezione anti-nuke del server."
    )

    @anti_nuke_group.command(name="enable", description="Attiva o disattiva l'Anti-Nuke.")
    @app_commands.checks.has_permissions(manage_guild=True)
    @requires_module(MODULE_ANTI_NUKE)
    async def enable(self, interaction: discord.Interaction, enabled: bool) -> None:
        if not await ensure_module_enabled(interaction, MODULE_ANTI_NUKE):
            return
        settings = await security_repo.get_settings(interaction.guild.id)
        await security_repo.save_settings(_replace(settings, enabled=enabled))
        await interaction.response.send_message(f"Anti-Nuke {'attivato' if enabled else 'disattivato'}.", ephemeral=True)

    @anti_nuke_group.command(name="limits", description="Configura la soglia di rilevamento per una categoria.")
    @app_commands.describe(max_actions="Numero massimo di azioni consentite nella finestra", seconds="Finestra in secondi")
    @app_commands.choices(
        category=[
            app_commands.Choice(name="Canali", value=NUKE_CATEGORY_CHANNEL),
            app_commands.Choice(name="Ruoli", value=NUKE_CATEGORY_ROLE),
            app_commands.Choice(name="Webhook", value=NUKE_CATEGORY_WEBHOOK),
            app_commands.Choice(name="Emoji/Sticker", value=NUKE_CATEGORY_EMOJI),
            app_commands.Choice(name="Ban/Kick", value=NUKE_CATEGORY_BAN_KICK),
        ]
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    @requires_module(MODULE_ANTI_NUKE)
    async def limits(
        self, interaction: discord.Interaction, category: app_commands.Choice[str], max_actions: int, seconds: int
    ) -> None:
        if not await ensure_module_enabled(interaction, MODULE_ANTI_NUKE):
            return
        settings = await security_repo.get_settings(interaction.guild.id)
        campo_max = {
            NUKE_CATEGORY_CHANNEL: "channel_max", NUKE_CATEGORY_ROLE: "role_max",
            NUKE_CATEGORY_WEBHOOK: "webhook_max", NUKE_CATEGORY_EMOJI: "emoji_max",
            NUKE_CATEGORY_BAN_KICK: "ban_kick_max",
        }[category.value]
        campo_finestra = {
            NUKE_CATEGORY_CHANNEL: "channel_window_seconds", NUKE_CATEGORY_ROLE: "role_window_seconds",
            NUKE_CATEGORY_WEBHOOK: "webhook_window_seconds", NUKE_CATEGORY_EMOJI: "emoji_window_seconds",
            NUKE_CATEGORY_BAN_KICK: "ban_kick_window_seconds",
        }[category.value]
        await security_repo.save_settings(
            _replace(settings, **{campo_max: max_actions, campo_finestra: seconds})
        )
        await interaction.response.send_message(
            f"Soglia **{category.name}** impostata a {max_actions} ogni {seconds}s.", ephemeral=True
        )

    @anti_nuke_group.command(name="trusted-add", description="Esenta un utente/bot fidato da tutti i controlli Anti-Nuke.")
    @app_commands.checks.has_permissions(manage_guild=True)
    @requires_module(MODULE_ANTI_NUKE)
    async def trusted_add(self, interaction: discord.Interaction, user_id: str) -> None:
        if not await ensure_module_enabled(interaction, MODULE_ANTI_NUKE):
            return
        try:
            id_utente = int(user_id)
        except ValueError:
            await interaction.response.send_message("ID utente non valido.", ephemeral=True)
            return
        settings = await security_repo.get_settings(interaction.guild.id)
        if id_utente not in settings.anti_nuke.trusted_ids:
            await security_repo.save_settings(
                _replace(settings, trusted_ids=settings.anti_nuke.trusted_ids + (id_utente,))
            )
        await interaction.response.send_message(f"Utente `{id_utente}` esentato dai controlli Anti-Nuke.", ephemeral=True)

    @anti_nuke_group.command(name="trusted-remove", description="Rimuove un utente/bot dalla lista fidati Anti-Nuke.")
    @app_commands.checks.has_permissions(manage_guild=True)
    @requires_module(MODULE_ANTI_NUKE)
    async def trusted_remove(self, interaction: discord.Interaction, user_id: str) -> None:
        if not await ensure_module_enabled(interaction, MODULE_ANTI_NUKE):
            return
        try:
            id_utente = int(user_id)
        except ValueError:
            await interaction.response.send_message("ID utente non valido.", ephemeral=True)
            return
        settings = await security_repo.get_settings(interaction.guild.id)
        await security_repo.save_settings(
            _replace(settings, trusted_ids=tuple(i for i in settings.anti_nuke.trusted_ids if i != id_utente))
        )
        await interaction.response.send_message(f"Utente `{id_utente}` rimosso dalla lista fidati.", ephemeral=True)

    @anti_nuke_group.command(name="punish-action", description="Cosa fare all'autore di un'azione distruttiva di massa.")
    @app_commands.choices(
        action=[
            app_commands.Choice(name="Rimuovi tutti i ruoli (un bot viene espulso)", value="strip_roles"),
            app_commands.Choice(name="Banna", value="ban"),
        ]
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    @requires_module(MODULE_ANTI_NUKE)
    async def punish_action(self, interaction: discord.Interaction, action: app_commands.Choice[str]) -> None:
        if not await ensure_module_enabled(interaction, MODULE_ANTI_NUKE):
            return
        settings = await security_repo.get_settings(interaction.guild.id)
        await security_repo.save_settings(_replace(settings, punish_action=action.value))
        await interaction.response.send_message(f"Azione punitiva impostata su **{action.name}**.", ephemeral=True)

    @anti_nuke_group.command(name="recovery", description="Attiva/disattiva la ricreazione automatica di canali/ruoli cancellati durante un attacco.")
    @app_commands.checks.has_permissions(manage_guild=True)
    @requires_module(MODULE_ANTI_NUKE)
    async def recovery(self, interaction: discord.Interaction, enabled: bool) -> None:
        if not await ensure_module_enabled(interaction, MODULE_ANTI_NUKE):
            return
        settings = await security_repo.get_settings(interaction.guild.id)
        await security_repo.save_settings(_replace(settings, recovery_enabled=enabled))
        await interaction.response.send_message(f"Recovery automatico {'attivato' if enabled else 'disattivato'}.", ephemeral=True)

    @anti_nuke_group.command(name="status", description="Mostra la configurazione attuale dell'Anti-Nuke.")
    @requires_module(MODULE_ANTI_NUKE)
    async def status(self, interaction: discord.Interaction) -> None:
        if not await ensure_module_enabled(interaction, MODULE_ANTI_NUKE):
            return
        settings = await security_repo.get_settings(interaction.guild.id)
        n = settings.anti_nuke
        righe = [
            f"**Attivo**: {'sì' if n.enabled else 'no'}",
            f"**Canali**: max {n.channel_max}/{n.channel_window_seconds}s",
            f"**Ruoli**: max {n.role_max}/{n.role_window_seconds}s",
            f"**Webhook**: max {n.webhook_max}/{n.webhook_window_seconds}s",
            f"**Emoji/Sticker**: max {n.emoji_max}/{n.emoji_window_seconds}s",
            f"**Ban/Kick**: max {n.ban_kick_max}/{n.ban_kick_window_seconds}s",
            f"**Azione punitiva**: {n.punish_action}",
            f"**Recovery automatico**: {'sì' if n.recovery_enabled else 'no'}",
            f"**Utenti fidati**: {len(n.trusted_ids)}",
        ]
        await interaction.response.send_message("\n".join(righe), ephemeral=True)

    # ================================================================
    # Motore di rilevamento — un metodo condiviso per ogni categoria,
    # così la logica "conta -> valuta -> punisci -> logga -> alert" non
    # si ripete cinque volte quasi identica.
    # ================================================================
    async def _impostazioni_attive(self, guild: discord.Guild) -> SecuritySettings | None:
        """Le impostazioni del server se l'anti-nuke è attivo lì, altrimenti None."""
        if not await db.is_module_active_for_guild(guild.id, MODULE_ANTI_NUKE):
            return None
        if not await premium_sbloccato(guild.id, MODULE_ANTI_NUKE, self.bot):
            return None
        settings = await security_repo.get_settings(guild.id)
        return settings if settings.anti_nuke.enabled else None

    async def _evento(
        self,
        guild: discord.Guild,
        category: str,
        azioni: tuple[discord.AuditLogAction, ...],
        detail_suffix: str,
        target_id: int | None = None,
        attese: tuple[float, ...] = ATTESE_REGISTRO,
        cancellato: discord.abc.GuildChannel | discord.Role | None = None,
    ) -> SecuritySettings | None:
        """
        Percorso comune dei listener. Prima si controlla se l'anti-nuke
        è attivo: dove è spento il registro di controllo non viene
        letto. Poi si cerca l'autore (nella prima delle `azioni` che ha
        una voce) e si passa al motore.

        Se è passato l'oggetto `cancellato`, lo si tiene da parte per
        quell'autore: sotto soglia non si ricrea nulla, ma appena
        l'autore la supera si recupera anche ciò che aveva già
        cancellato prima (e, se il recupero è attivo, ogni
        cancellazione successiva).
        """
        settings = await self._impostazioni_attive(guild)
        if settings is None:
            return None
        actor_id = None
        for azione in azioni:
            actor_id = await _resolve_actor(guild, azione, target_id, attese)
            if actor_id is not None:
                break
        if cancellato is not None and actor_id is not None and actor_id != self.bot.user.id:
            chiave = (guild.id, actor_id)
            in_attesa = self._in_attesa.get(chiave) or []
            in_attesa.append(cancellato)
            self._in_attesa.set(chiave, in_attesa[-MAX_IN_ATTESA:])
        violazione = await self._handle_event(guild, category, actor_id, detail_suffix, settings)
        if violazione is not None and cancellato is not None and violazione.anti_nuke.recovery_enabled:
            await self._recupera_in_attesa(guild.id, actor_id)
        return violazione

    async def _recupera_in_attesa(self, guild_id: int, actor_id: int) -> None:
        """Ricrea tutto ciò che l'autore ha cancellato: prima le categorie, poi il resto."""
        chiave = (guild_id, actor_id)
        in_attesa = list(self._in_attesa.get(chiave) or [])
        self._in_attesa.delete(chiave)
        in_attesa.sort(key=lambda oggetto: not isinstance(oggetto, discord.CategoryChannel))
        for oggetto in in_attesa:
            try:
                if isinstance(oggetto, discord.Role):
                    await self._ricrea_ruolo(oggetto)
                else:
                    await self._ricrea_canale(oggetto)
            except discord.HTTPException as errore:
                logger.warning("Recovery di %s fallita: %s", getattr(oggetto, "name", "?"), errore)

    async def _handle_event(
        self,
        guild: discord.Guild,
        category: str,
        actor_id: int | None,
        detail_suffix: str,
        settings: SecuritySettings | None = None,
    ) -> SecuritySettings | None:
        # Le azioni del bot stesso (recovery, ticket, canali temporanei)
        # non si contano: il bot non deve mai punire se stesso.
        if actor_id is None or actor_id == self.bot.user.id:
            return None
        if settings is None:
            settings = await self._impostazioni_attive(guild)
            if settings is None:
                return None

        now = discord.utils.utcnow()
        finestra = category_window_seconds(category, settings.anti_nuke)
        conteggio = security_rate_tracker.record_and_count(guild.id, actor_id, category, now, finestra)

        if not is_nuke_violation(actor_id, category, conteggio, settings.anti_nuke):
            return None

        esito = await _punish_actor(
            guild, actor_id, settings.anti_nuke, reason=f"Anti-Nuke: {category} — {detail_suffix}"
        )
        dettaglio = f"{detail_suffix} — {conteggio} azioni in {finestra}s — {esito}"
        await security_repo.log_action(guild.id, f"nuke_{category}", actor_id, dettaglio)

        embed = discord.Embed(
            title=f"🚨 Anti-Nuke — {category}", description=dettaglio, color=discord.Color.red()
        )
        await _alert_staff(guild, settings, embed)
        return settings

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel) -> None:
        await self._evento(
            channel.guild, NUKE_CATEGORY_CHANNEL, (discord.AuditLogAction.channel_create,),
            f"creato #{channel.name}", target_id=channel.id,
        )

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> None:
        await self._evento(
            channel.guild, NUKE_CATEGORY_CHANNEL, (discord.AuditLogAction.channel_delete,),
            f"cancellato #{channel.name}", target_id=channel.id, cancellato=channel,
        )

    async def _ricrea_canale(self, channel: discord.abc.GuildChannel) -> None:
        """
        Ricrea un canale cancellato, dello stesso tipo, con nome,
        permessi, posizione e (dove esiste) argomento. I messaggi non
        si possono recuperare.
        """
        if channel.name == NOME_CANALE_NASCOSTO:
            # Canale che il bot non poteva vedere: Discord ne dà solo
            # un nome finto, ricrearlo sarebbe un danno.
            return

        guild = channel.guild
        opzioni: dict = {
            "name": channel.name,
            "position": channel.position,
            # I permessi di ruoli o membri spariti (Object) farebbero
            # rifiutare a Discord tutta la creazione.
            "overwrites": {
                bersaglio: permessi
                for bersaglio, permessi in channel.overwrites.items()
                if not isinstance(bersaglio, discord.Object)
            },
            "reason": MOTIVO_RECOVERY,
        }

        if isinstance(channel, discord.CategoryChannel):
            nuova = await guild.create_category(**opzioni)
            self._categorie_ricreate.set(channel.id, nuova)
            return

        # Se anche la categoria è stata cancellata e ricreata, il
        # canale torna in quella nuova.
        opzioni["category"] = channel.category or self._categorie_ricreate.get(channel.category_id)

        if isinstance(channel, (discord.TextChannel, discord.ForumChannel)):
            if channel.topic:
                opzioni["topic"] = channel.topic
            opzioni["nsfw"] = channel.nsfw
            opzioni["slowmode_delay"] = channel.slowmode_delay
            if isinstance(channel, discord.TextChannel):
                await guild.create_text_channel(news=channel.is_news(), **opzioni)
            else:
                # I tag si ricreano nuovi (stesso nome, emoji, moderazione):
                # gli ID vecchi non esistono più.
                opzioni["available_tags"] = [
                    discord.ForumTag(name=tag.name, emoji=tag.emoji, moderated=tag.moderated)
                    for tag in channel.available_tags
                ]
                await guild.create_forum(media=channel.is_media(), **opzioni)
        elif isinstance(channel, (discord.VoiceChannel, discord.StageChannel)):
            # La qualità audio non può superare quella che il server
            # ha adesso (dipende dai boost).
            opzioni["bitrate"] = min(channel.bitrate, int(guild.bitrate_limit))
            opzioni["user_limit"] = channel.user_limit
            if isinstance(channel, discord.StageChannel):
                await guild.create_stage_channel(**opzioni)
            else:
                await guild.create_voice_channel(nsfw=channel.nsfw, **opzioni)

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role) -> None:
        await self._evento(
            role.guild, NUKE_CATEGORY_ROLE, (discord.AuditLogAction.role_create,),
            f"creato ruolo {role.name}", target_id=role.id,
        )

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role) -> None:
        await self._evento(
            role.guild, NUKE_CATEGORY_ROLE, (discord.AuditLogAction.role_delete,),
            f"cancellato ruolo {role.name}", target_id=role.id, cancellato=role,
        )

    async def _ricrea_ruolo(self, role: discord.Role) -> None:
        """
        Ricrea un ruolo cancellato con le stesse impostazioni, nella
        posizione di prima (mai sopra il ruolo più alto del bot) e
        rimette il ruolo ai membri che lo avevano.
        """
        guild = role.guild
        nuovo = await guild.create_role(
            name=role.name,
            permissions=role.permissions,
            colour=role.colour,
            hoist=role.hoist,
            mentionable=role.mentionable,
            reason=MOTIVO_RECOVERY,
        )
        massima = guild.me.top_role.position - 1
        posizione = min(role.position, massima)
        if posizione >= 1:
            try:
                await nuovo.edit(position=posizione, reason=MOTIVO_RECOVERY)
            except discord.HTTPException as errore:
                logger.warning("Posizione del ruolo %s non ripristinata: %s", role.name, errore)

        membri = list(role.members)
        if len(membri) > MAX_MEMBRI_RIPRISTINO:
            logger.warning(
                "Ruolo %s: %d membri, ne rimetto solo %d.",
                role.name, len(membri), MAX_MEMBRI_RIPRISTINO,
            )
        for membro in membri[:MAX_MEMBRI_RIPRISTINO]:
            try:
                await membro.add_roles(nuovo, reason=MOTIVO_RECOVERY)
            except discord.HTTPException:
                continue

    @commands.Cog.listener()
    async def on_webhooks_update(self, channel: discord.abc.GuildChannel) -> None:
        await self._evento(
            channel.guild, NUKE_CATEGORY_WEBHOOK,
            (discord.AuditLogAction.webhook_create, discord.AuditLogAction.webhook_delete),
            f"webhook modificati in #{channel.name}",
        )

    @commands.Cog.listener()
    async def on_guild_emojis_update(self, guild: discord.Guild, before, after) -> None:
        # Le sound board non sono contate qui: emoji e sticker (sotto) sì.
        azione = discord.AuditLogAction.emoji_create if len(after) > len(before) else discord.AuditLogAction.emoji_delete
        await self._evento(guild, NUKE_CATEGORY_EMOJI, (azione,), "emoji del server modificate")

    @commands.Cog.listener()
    async def on_guild_stickers_update(self, guild: discord.Guild, before, after) -> None:
        azione = discord.AuditLogAction.sticker_create if len(after) > len(before) else discord.AuditLogAction.sticker_delete
        await self._evento(guild, NUKE_CATEGORY_EMOJI, (azione,), "sticker del server modificati")

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.abc.User) -> None:
        await self._evento(
            guild, NUKE_CATEGORY_BAN_KICK, (discord.AuditLogAction.ban,),
            f"ban di {user}", target_id=user.id,
        )

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        # on_member_remove scatta anche per un'uscita volontaria: si
        # conta solo se nel registro c'è davvero un kick di questo
        # membro (senza voce il motore non conta niente).
        await self._evento(
            member.guild, NUKE_CATEGORY_BAN_KICK, (discord.AuditLogAction.kick,),
            f"kick di {member}", target_id=member.id, attese=ATTESE_REGISTRO_USCITA,
        )


async def setup(bot: commands.Bot) -> None:
    registry.register(
        PremiumModule(
            name=MODULE_ANTI_NUKE,
            display_name="Anti-Nuke",
            category="security",
            description="Rilevamento e risposta automatica ad azioni distruttive di massa sul server.",
            premium_capable=True,
        )
    )
    await bot.add_cog(AntiNukeCog(bot))
