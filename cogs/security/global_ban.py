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

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

import discord
from discord import app_commands
from discord.ext import commands

from core.command_groups import CogConGruppi, comando_di_gruppo

from core.database import db
from core.global_ban_logic import should_propagate_ban
from core.premium import PremiumModule, registry, requires_module
from core.repositories.global_ban_repo import global_ban_repo
from core.security_access import SETTING_STAFF_ROLES, is_staff_exempt, premium_sbloccato

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


@dataclass
class _Episodio:
    """
    Una propagazione (o la sua revoca) per (server sorgente, utente). La
    propagazione tiene il blocco finche' gira; una revoca arrivata nel
    mezzo alza `revocato`, la propagazione si ferma al ban successivo e la
    revoca, quando prende il blocco, trova il registro completo di cio' che
    e' partito. Cosi' dopo un appello accolto non parte nessun ban in piu'.
    """

    blocco: asyncio.Lock = field(default_factory=asyncio.Lock)
    revocato: bool = False
    in_uso: int = 0


_episodi: dict[tuple[int, int], _Episodio] = {}


def _prendi_episodio(chiave: tuple[int, int]) -> _Episodio:
    episodio = _episodi.get(chiave)
    if episodio is None:
        episodio = _episodi[chiave] = _Episodio()
    episodio.in_uso += 1
    return episodio


def _lascia_episodio(chiave: tuple[int, int], episodio: _Episodio) -> None:
    episodio.in_uso -= 1
    if episodio.in_uso <= 0 and _episodi.get(chiave) is episodio:
        del _episodi[chiave]


async def _banna_e_registra(
    target: discord.Guild, source_guild: discord.Guild, user_id: int, reason: str
) -> bool:
    """Un ban sul server di arrivo e la riga nel registro, come un'unica operazione."""
    try:
        await target.ban(
            discord.Object(id=user_id),
            reason=f"{PREFISSO_MOTIVO} — Spam Trap innescata su {source_guild.name}: {reason}"[:512],
            delete_message_seconds=0,
        )
    except discord.Forbidden:
        logger.warning(
            "Ban globale: permessi insufficienti per bannare %s nel server %s.", user_id, target.id
        )
        return False
    except discord.HTTPException:
        logger.warning(
            "Ban globale: errore HTTP bannando %s nel server %s (probabilmente già bannato).",
            user_id, target.id,
        )
        return False
    await global_ban_repo.log_propagation(source_guild.id, target.id, user_id, reason)
    return True


async def _staff_nel_server(target: discord.Guild, user_id: int) -> bool:
    """L'utente e' staff (admin/mod, un bot, ruolo staff) nel server di arrivo? Lo staff non si banna."""
    membro = target.get_member(user_id)
    if membro is None:
        return False
    ruoli = await db.get_guild_setting(target.id, SETTING_STAFF_ROLES, default=[])
    return is_staff_exempt(membro, target, set(ruoli or ()))


async def propagate_ban(
    bot: commands.Bot, source_guild: discord.Guild, user_id: int, reason: str
) -> list[int]:
    """
    Chiamata dalla Spam Trap (§7.3) subito dopo un ban confermato.
    Restituisce la lista degli ID dei server in cui il ban è stato
    effettivamente propagato (per il log di chi ha chiamato).

    Il server sorgente deve avere acceso "invia", quello di arrivo
    "ricevi" (SIC-046). Chi nel server di arrivo e' staff (amministratore,
    moderatore, ruolo staff della Spam Trap) o un bot non viene bannato
    li': una Spam Trap altrui non puo' togliere un admin al suo server.

    Best-effort: un fallimento (permessi insufficienti, rate limit,
    utente già bannato lì) su UN server target non deve bloccare la
    propagazione verso gli altri — viene solo loggato e saltato. Se nel
    frattempo l'appello viene accolto (`revoca_ban_propagati`) si ferma.
    """
    source_invia, _ = await _direzioni(bot, source_guild.id)
    if not source_invia:
        return []

    # La pulizia del registro vecchio una volta per giro, non a ogni riga.
    await global_ban_repo.purge_old()

    chiave = (source_guild.id, user_id)
    episodio = _prendi_episodio(chiave)
    propagati: list[int] = []
    try:
        async with episodio.blocco:
            for target in list(bot.guilds):
                if episodio.revocato:
                    break
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
                if await _staff_nel_server(target, user_id):
                    logger.info(
                        "Ban globale: %s è staff nel server %s, non lo banno lì.", user_id, target.id
                    )
                    continue
                # Il ban e la sua riga di registro non si spezzano se chi chiama viene annullato.
                if not await asyncio.shield(_banna_e_registra(target, source_guild, user_id, reason)):
                    continue
                propagati.append(target.id)
                if PAUSA_TRA_I_BAN:
                    await asyncio.sleep(PAUSA_TRA_I_BAN)
    finally:
        _lascia_episodio(chiave, episodio)
    return propagati


async def revoca_ban_propagati(bot: commands.Bot, source_guild_id: int, user_id: int) -> int:
    """
    L'appello è stato accolto: toglie il ban anche dai server in cui era
    arrivato da qui. Si tocca solo un ban che porta il motivo della rete:
    uno messo a mano dallo staff di quel server resta, e resta anche se un
    altro server della rete lo ha bannato lì e il suo ban è ancora in piedi.
    Un ban che Discord non lascia togliere resta nel registro e si ritenta
    alla prossima revoca. Restituisce in quanti server il ban è stato tolto.
    """
    chiave = (source_guild_id, user_id)
    episodio = _prendi_episodio(chiave)
    episodio.revocato = True  # una propagazione in corso si ferma al ban successivo
    tolti = 0
    chiusi: list[int] = []
    try:
        async with episodio.blocco:
            for target_id in await global_ban_repo.active_propagations(source_guild_id, user_id):
                target = bot.get_guild(target_id)
                if target is None:
                    continue
                if await global_ban_repo.banned_by_other_source(target_id, user_id, source_guild_id):
                    chiusi.append(target_id)  # il nostro ban e' chiuso, quello dell'altra sorgente tiene
                    continue
                try:
                    ban = await target.fetch_ban(discord.Object(id=user_id))
                    if not (ban.reason or "").startswith(PREFISSO_MOTIVO):
                        chiusi.append(target_id)  # ban dello staff di quel server: non e' nostro
                        continue
                    await target.unban(
                        discord.Object(id=user_id), reason="Ban globale revocato: appello accolto"
                    )
                    tolti += 1
                    chiusi.append(target_id)
                except discord.NotFound:
                    chiusi.append(target_id)  # già sbannato lì
                except discord.HTTPException:
                    logger.warning(
                        "Ban globale: impossibile togliere %s dal server %s, resta da ritentare.",
                        user_id, target_id,
                    )
                if PAUSA_TRA_I_BAN:
                    await asyncio.sleep(PAUSA_TRA_I_BAN)
            await global_ban_repo.mark_revoked(source_guild_id, user_id, chiusi)
    finally:
        _lascia_episodio(chiave, episodio)
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
        nome="controlla",
        descrizione="Da quanti server della rete questo utente è stato bannato dalla Spam Trap.",
        sottogruppo=("globalban", "Rete di ban globali tra server."),
    )
    @app_commands.describe(utente="L'utente da controllare (anche se non è nel server)")
    @requires_module(MODULE_GLOBAL_BAN)
    async def controlla(self, interaction: discord.Interaction, utente: discord.User) -> None:
        if not await _aderisce(self.bot, interaction.guild.id):
            await interaction.response.send_message(
                "Solo i server che partecipano alla rete possono consultarla: /security globalban enable.",
                ephemeral=True,
            )
            return
        server, primo, ultimo = await global_ban_repo.network_summary(utente.id)
        if server == 0:
            testo = f"Nessun server della rete ha bannato {utente.mention} con la Spam Trap."
        else:
            testo = (
                f"{utente.mention} è stato bannato dalla Spam Trap da {server} server della rete "
                f"(primo ban {discord.utils.format_dt(primo, 'd')}, ultimo {discord.utils.format_dt(ultimo, 'd')}). "
                "Non mostro quali server: conta solo il numero."
            )
        await interaction.response.send_message(
            testo, ephemeral=True, allowed_mentions=discord.AllowedMentions.none()
        )

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
