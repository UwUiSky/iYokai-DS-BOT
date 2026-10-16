"""
core/bot_roles.py
=================
Un solo punto che decide quale bot esegue log e azioni di sicurezza in un
server (D15): iYokai Mod se c'è, è collegato, ha il permesso e non è
fermo per un rate limit lungo; altrimenti il bot principale, come prima.
Gli eventi li ascolta solo il principale (Mod non ha listener né comandi):
così ogni evento ha un solo gestore e niente esce doppio.
Funzioni coperte: SPEC parte E (iYokai Mod, D15)
"""

from __future__ import annotations

import logging
import time
from typing import Awaitable, Callable

import discord

logger = logging.getLogger("iyokai.bot_roles")

# Permessi minimi per scrivere un log in un canale.
PERMESSI_LOG = ("view_channel", "send_messages", "embed_links")

_mod: discord.Client | None = None
_fermo_fino: float = 0.0  # time.monotonic() prima del quale Mod non si usa


def registra_mod(client: discord.Client | None) -> None:
    """Collega il client di iYokai Mod (None lo scollega). Lo chiama solo main.py."""
    global _mod, _fermo_fino
    _mod = client
    _fermo_fino = 0.0


def client_mod() -> discord.Client | None:
    """Il client di Mod, se è stato avviato (anche se ora non è collegato)."""
    return _mod


def e_un_nostro_bot(user_id: int | None, principale: discord.Client) -> bool:
    """True per il bot principale e per Mod: le loro azioni non contano come attacchi."""
    if user_id is None:
        return False
    if principale.user is not None and user_id == principale.user.id:
        return True
    return _mod is not None and _mod.user is not None and user_id == _mod.user.id


def segna_fermo(secondi: float) -> None:
    """Mod ha preso un rate limit lungo: per `secondi` fa tutto il principale."""
    global _fermo_fino
    _fermo_fino = max(_fermo_fino, time.monotonic() + max(0.0, secondi))
    logger.warning("iYokai Mod in rate limit per %.0f s: lavora il bot principale.", secondi)


def _mod_attivo() -> bool:
    return (
        _mod is not None
        and _mod.is_ready()
        and not _mod.is_closed()
        and time.monotonic() >= _fermo_fino
    )


def server_mod(guild_id: int) -> discord.Guild | None:
    """Il server visto da Mod, se Mod è attivo e ci si trova; altrimenti None."""
    if not _mod_attivo():
        return None
    return _mod.get_guild(guild_id)


def _posizione(bersaglio) -> int:
    ruolo = getattr(bersaglio, "top_role", bersaglio)
    return getattr(ruolo, "position", 0)


def esecutore(guild: discord.Guild, permesso: str | None = None, sopra=None) -> discord.Client | None:
    """
    Il client di Mod se in questo server deve agire lui, altrimenti None
    (agisce il principale). `permesso` è un nome di discord.Permissions;
    `sopra` è un membro o un ruolo che Mod deve superare in gerarchia.
    """
    server = server_mod(guild.id)
    if server is None or server.me is None:
        return None
    permessi = server.me.guild_permissions
    if permesso and not (permessi.administrator or getattr(permessi, permesso, False)):
        return None
    if sopra is not None and server.me.top_role.position <= _posizione(sopra):
        return None
    return _mod


def canale(canale_principale, permessi: tuple[str, ...] = PERMESSI_LOG):
    """
    Lo stesso canale visto da Mod, se Mod deve scriverci; altrimenti il
    canale del principale così com'è.
    """
    guild = getattr(canale_principale, "guild", None)
    if guild is None:
        return canale_principale
    server = server_mod(guild.id)
    if server is None or server.me is None:
        return canale_principale
    suo = server.get_channel(canale_principale.id)
    if suo is None:
        return canale_principale
    concessi = suo.permissions_for(server.me)
    if not all(getattr(concessi, nome, False) for nome in permessi):
        return canale_principale
    return suo


async def scrivi(canale_principale, **kw):
    """
    Manda un messaggio di log con un solo bot: Mod se può, altrimenti il
    principale. Con bottoni (`view`) scrive sempre il principale, che li gestisce.
    """
    dest = canale(canale_principale)
    if dest is canale_principale or kw.get("view") is not None:
        return await canale_principale.send(**kw)
    try:
        return await dest.send(**kw)
    except discord.RateLimited as errore:
        segna_fermo(errore.retry_after)
    except discord.Forbidden:
        logger.info("iYokai Mod non può scrivere nel canale %s: scrive il principale.", canale_principale.id)
    for file in [kw.get("file"), *(kw.get("files") or [])]:
        if file is not None:
            file.reset()
    return await canale_principale.send(**kw)


def e_di_mod(oggetto) -> bool:
    """True se l'oggetto (canale, server) appartiene alla cache di Mod."""
    if _mod is None:
        return False
    guild = oggetto if isinstance(oggetto, discord.Guild) else getattr(oggetto, "guild", None)
    return guild is not None and _mod.get_guild(guild.id) is guild


async def esegui(
    guild: discord.Guild,
    permesso: str,
    principale: Callable[[], Awaitable],
    via_mod: Callable[[discord.Client], Awaitable],
    sopra=None,
):
    """
    Esegue un'azione con un solo bot. `principale()` è la chiamata di
    sempre; `via_mod(client)` la stessa fatta con Mod. Se Mod non può
    (permesso tolto, rate limit lungo) la rifà il principale: una volta
    sola, e solo per errori che dicono che l'azione non è avvenuta.
    """
    client = esecutore(guild, permesso, sopra)
    if client is None:
        return await principale()
    try:
        return await via_mod(client)
    except discord.RateLimited as errore:
        segna_fermo(errore.retry_after)
    except discord.Forbidden:
        logger.info("iYokai Mod senza permesso %s nel server %s: agisce il principale.", permesso, guild.id)
    return await principale()


# --- Azioni pronte (le usano AutoMod, anti-raid, anti-nuke, spam-trap, scadenze)


async def banna(guild: discord.Guild, utente, *, reason: str | None, delete_message_seconds: int = 0, principale=None):
    """Ban con un solo bot. `principale` sostituisce la chiamata di sempre (es. member.ban)."""
    return await esegui(
        guild,
        "ban_members",
        principale or (lambda: guild.ban(utente, reason=reason, delete_message_seconds=delete_message_seconds)),
        lambda c: c.http.ban(utente.id, guild.id, delete_message_seconds, reason=reason),
        sopra=utente if isinstance(utente, discord.Member) else None,
    )


async def sbanna(guild: discord.Guild, utente, *, reason: str | None):
    return await esegui(
        guild,
        "ban_members",
        lambda: guild.unban(utente, reason=reason),
        lambda c: c.http.unban(utente.id, guild.id, reason=reason),
    )


async def espelli(membro: discord.Member, *, reason: str | None):
    return await esegui(
        membro.guild,
        "kick_members",
        lambda: membro.kick(reason=reason),
        lambda c: c.http.kick(membro.id, membro.guild.id, reason=reason),
        sopra=membro,
    )


async def isola(membro: discord.Member, durata, *, reason: str | None):
    """Timeout (durata: timedelta o datetime) con un solo bot."""
    fino = discord.utils.utcnow() + durata if hasattr(durata, "total_seconds") else durata
    return await esegui(
        membro.guild,
        "moderate_members",
        lambda: membro.timeout(durata, reason=reason),
        lambda c: c.http.edit_member(
            membro.guild.id, membro.id, reason=reason, communication_disabled_until=fino.isoformat() if fino else None
        ),
        sopra=membro,
    )


async def aggiungi_ruolo(membro: discord.Member, ruolo: discord.Role, *, reason: str | None):
    return await esegui(
        membro.guild,
        "manage_roles",
        lambda: membro.add_roles(ruolo, reason=reason),
        lambda c: c.http.add_role(membro.guild.id, membro.id, ruolo.id, reason=reason),
        sopra=ruolo,
    )


async def imposta_ruoli(membro: discord.Member, ruoli: list, *, reason: str | None):
    """Sostituisce i ruoli del membro (come member.edit(roles=...))."""
    return await esegui(
        membro.guild,
        "manage_roles",
        lambda: membro.edit(roles=ruoli, reason=reason),
        lambda c: c.http.edit_member(membro.guild.id, membro.id, reason=reason, roles=[r.id for r in ruoli]),
        sopra=membro,
    )


async def cancella_messaggio(messaggio: discord.Message):
    canale_msg = messaggio.channel
    return await esegui(
        messaggio.guild,
        "manage_messages",
        lambda: messaggio.delete(),
        lambda c: c.http.delete_message(canale_msg.id, messaggio.id),
    )


async def cancella_messaggi(canale_msg, messaggi: list):
    """Cancellazione in blocco (2–100 messaggi recenti) con un solo bot."""
    return await esegui(
        canale_msg.guild,
        "manage_messages",
        lambda: canale_msg.delete_messages(messaggi),
        lambda c: _cancella_via_mod(c, canale_msg.id, [m.id for m in messaggi]),
    )


async def _cancella_via_mod(client: discord.Client, channel_id: int, ids: list[int]):
    """Come TextChannel.delete_messages: Discord rifiuta il blocco con meno di 2 messaggi."""
    if not ids:
        return None
    if len(ids) == 1:
        return await client.http.delete_message(channel_id, ids[0])
    return await client.http.delete_messages(channel_id, ids)
