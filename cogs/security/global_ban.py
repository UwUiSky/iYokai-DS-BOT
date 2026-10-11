"""
cogs/security/global_ban.py
================================
Ban globale (SPEC.md §7.3) — propagazione cross-server di un ban
scattato dalla Spam Trap (§7.3) verso ogni altro server che condivide
il bot E ha aderito alla stessa rete di ban globali. Modulo CANDIDATO
PREMIUM (come Spam Trap/Anti-Raid/Anti-Nuke).

Vedi core/global_ban_logic.py per la nota di design completa sul
perché questo è distinto dal ban globale via fingerprint/alt-
detection descritto in SPEC.md §4.3 (quello resta bloccato,
correttamente, sulla dipendenza da §4.2 — raccolta OAuth2 al momento
del verify — non costruita): qui si banna lo STESSO account Discord
(stesso user id) su ogni server aderente, non un account diverso
sospettato di essere un alt.

L'opt-in usa l'attivazione modulo già esistente
(`db.is_module_active_for_guild`/`set_module_active_for_guild`,
MODULE_GLOBAL_BAN) — nessuna tabella di configurazione dedicata,
vedi core/repositories/global_ban_repo.py. Reciprocità: un ban
scattato nel server A si propaga al server B SOLO SE entrambi hanno
il modulo attivo — un server che non ha aderito non riceve mai un
ban deciso altrove.
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

from core.command_groups import CogConGruppi, comando_di_gruppo

from core.database import db
from core.global_ban_logic import should_propagate_ban
from core.premium import PremiumModule, registry, requires_module
from core.repositories.global_ban_repo import global_ban_repo
from core.security_access import premium_sbloccato

logger = logging.getLogger("iyokai.global_ban")

MODULE_GLOBAL_BAN = "global_ban"

# Pausa tra un ban propagato e il successivo: la rete puo' avere migliaia di
# server e Discord non vuole raffiche di richieste (LIMITI.md, Parte 4, punto 17).
PAUSA_TRA_I_BAN = 0.2

# Il motivo con cui i ban propagati partono: serve a riconoscerli quando si tolgono.
PREFISSO_MOTIVO = "Ban globale"


async def _aderisce(bot: commands.Bot, guild_id: int) -> bool:
    """Il server ha attivato il ban globale e, se il modulo è premium, lo ha sbloccato."""
    if not await db.is_module_active_for_guild(guild_id, MODULE_GLOBAL_BAN):
        return False
    return await premium_sbloccato(guild_id, MODULE_GLOBAL_BAN, bot)


async def _direzioni(bot: commands.Bot, guild_id: int) -> tuple[bool, bool]:
    """(invia, ricevi) del server: (False, False) se non partecipa alla rete."""
    if not await _aderisce(bot, guild_id):
        return False, False
    return await global_ban_repo.get_direction(guild_id)


async def propagate_ban(
    bot: commands.Bot, source_guild: discord.Guild, user_id: int, reason: str
) -> list[int]:
    """
    Chiamata dalla Spam Trap (§7.3) subito dopo un ban confermato.
    Restituisce la lista degli ID dei server in cui il ban è stato
    effettivamente propagato (per il log di chi ha chiamato).

    Il server sorgente deve avere acceso "invia", quello di arrivo
    "ricevi" (SIC-046).

    Best-effort: un fallimento (permessi insufficienti, rate limit,
    utente già bannato lì) su UN server target non deve bloccare la
    propagazione verso gli altri — viene solo loggato e saltato.
    """
    source_invia, _ = await _direzioni(bot, source_guild.id)
    if not source_invia:
        return []

    propagati: list[int] = []
    for target in list(bot.guilds):
        if target.id == source_guild.id:
            continue
        _, target_riceve = await _direzioni(bot, target.id)
        if not should_propagate_ban(
            source_guild_id=source_guild.id,
            target_guild_id=target.id,
            source_opted_in=source_invia,
            target_opted_in=target_riceve,
        ):
            continue

        try:
            await target.ban(
                discord.Object(id=user_id),
                reason=f"{PREFISSO_MOTIVO} — Spam Trap innescata su {source_guild.name}: {reason}"[:512],
                delete_message_seconds=0,
            )
        except discord.Forbidden:
            logger.warning(
                "Ban globale: permessi insufficienti per bannare %s nel server %s.",
                user_id, target.id,
            )
            continue
        except discord.HTTPException:
            logger.warning(
                "Ban globale: errore HTTP bannando %s nel server %s (probabilmente già bannato).",
                user_id, target.id,
            )
            continue

        await global_ban_repo.log_propagation(source_guild.id, target.id, user_id, reason)
        propagati.append(target.id)
        if PAUSA_TRA_I_BAN:
            await asyncio.sleep(PAUSA_TRA_I_BAN)

    return propagati


async def revoca_ban_propagati(bot: commands.Bot, source_guild_id: int, user_id: int) -> int:
    """
    L'appello è stato accolto: toglie il ban anche dai server in cui era
    arrivato da qui. Si tocca solo un ban che porta il motivo della rete:
    uno messo a mano dallo staff di quel server resta. Restituisce in
    quanti server il ban è stato tolto.
    """
    tolti = 0
    for target_id in await global_ban_repo.active_propagations(source_guild_id, user_id):
        target = bot.get_guild(target_id)
        if target is None:
            continue
        try:
            ban = await target.fetch_ban(discord.Object(id=user_id))
            if not (ban.reason or "").startswith(PREFISSO_MOTIVO):
                continue
            await target.unban(
                discord.Object(id=user_id), reason="Ban globale revocato: appello accolto"
            )
            tolti += 1
        except discord.NotFound:
            continue  # già sbannato lì
        except discord.HTTPException:
            logger.warning("Ban globale: impossibile togliere %s dal server %s.", user_id, target_id)
        if PAUSA_TRA_I_BAN:
            await asyncio.sleep(PAUSA_TRA_I_BAN)
    await global_ban_repo.mark_revoked(source_guild_id, user_id)
    return tolti


class GlobalBanCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @comando_di_gruppo(
        "security",
        nome="enable",
        descrizione="Aderisci alla rete di ban globali (propaga e ricevi).",
        sottogruppo=("globalban", "Rete di ban globali tra server."),
    )
    @app_commands.describe(
        invia="Propaga i ban della Spam Trap di questo server agli altri server della rete",
        ricevi="Applica qui i ban della Spam Trap degli altri server della rete",
    )
    @requires_module(MODULE_GLOBAL_BAN)
    async def enable(
        self, interaction: discord.Interaction, invia: bool = True, ricevi: bool = True
    ) -> None:
        if not invia and not ricevi:
            await interaction.response.send_message(
                "Scegli almeno una direzione: invia o ricevi. Per uscire dalla rete usa /security globalban disable.",
                ephemeral=True,
            )
            return
        await global_ban_repo.set_direction(interaction.guild.id, send=invia, receive=ricevi)
        await db.set_module_active_for_guild(
            interaction.guild.id, MODULE_GLOBAL_BAN, True, changed_by=interaction.user.id
        )
        cosa = []
        if invia:
            cosa.append("i ban della Spam Trap di questo server verranno propagati verso ogni altro server aderente")
        if ricevi:
            cosa.append("questo server riceverà i ban degli altri")
        await interaction.response.send_message(
            "✅ Ban globale attivato: " + ", e ".join(cosa) + ".", ephemeral=True
        )

    @comando_di_gruppo(
        "security",
        nome="disable",
        descrizione="Abbandona la rete di ban globali.",
        sottogruppo=("globalban", "Rete di ban globali tra server."),
    )
    async def disable(self, interaction: discord.Interaction) -> None:
        await db.set_module_active_for_guild(
            interaction.guild.id, MODULE_GLOBAL_BAN, False, changed_by=interaction.user.id
        )
        await interaction.response.send_message("❌ Ban globale disattivato.", ephemeral=True)

    @comando_di_gruppo(
        "security",
        nome="status",
        descrizione="Mostra lo stato e la storia recente del ban globale.",
        sottogruppo=("globalban", "Rete di ban globali tra server."),
    )
    @requires_module(MODULE_GLOBAL_BAN)
    async def status(self, interaction: discord.Interaction) -> None:
        attivo = await db.is_module_active_for_guild(interaction.guild.id, MODULE_GLOBAL_BAN)
        invia, ricevi = await global_ban_repo.get_direction(interaction.guild.id)
        outgoing = await global_ban_repo.get_recent_outgoing(interaction.guild.id, limit=5)
        incoming = await global_ban_repo.get_recent_incoming(interaction.guild.id, limit=5)

        embed = discord.Embed(
            title="🌐 Ban globale — stato",
            description=(
                f"**Attivo**: {'sì' if attivo else 'no'}\n"
                f"**Invia i miei ban**: {'sì' if invia else 'no'} · **Ricevo i ban degli altri**: {'sì' if ricevi else 'no'}"
            ),
            color=discord.Color.blue() if attivo else discord.Color.dark_gray(),
        )
        embed.add_field(
            name="Ban propagati da qui",
            value="\n".join(
                f"<@{e.user_id}> → server {e.target_guild_id}" for e in outgoing
            ) or "Nessuno.",
            inline=False,
        )
        embed.add_field(
            name="Ban ricevuti da altri server",
            value="\n".join(
                f"<@{e.user_id}> ← server {e.source_guild_id}" for e in incoming
            ) or "Nessuno.",
            inline=False,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    registry.register(
        PremiumModule(
            name=MODULE_GLOBAL_BAN,
            display_name="Ban Globale",
            category="security",
            description="Propaga i ban della Spam Trap verso ogni server aderente alla rete.",
            premium_capable=True,
        )
    )
    await bot.add_cog(GlobalBanCog(bot))
