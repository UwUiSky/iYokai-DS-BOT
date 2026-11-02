"""
core/verify_ip.py
=================
D67: gli IP di chi si verifica dalla pagina web, salvati CIFRATI (AES-256-GCM, `core/oauth_crypto.py`, chiave
`VERIFY_IP_ENCRYPTION_KEY`, legati a server e persona) per la sicurezza. Li vede SOLO il proprietario del bot
(`/owner system storico-vpn`, pagina `/proprietario/storico-vpn`): mai gli admin, mai i log, mai le eccezioni
(nei log finisce al massimo il tipo dell'errore). Senza chiave non si salva niente. Qui anche le scadenze:
30 giorni dopo l'uscita della persona o del bot dal server; dopo un kick 180 giorni; dopo un ban finché è
attivo e 30 giorni dopo lo sblocco; la cancellazione dei dati chiesta dalla persona (`/utility privacy cancella`) vale (tranne ban e kick, che si gestiscono a mano).
Funzioni coperte: SPEC §4.2 (IP solo per il proprietario, D67)
Dipende da: core/repositories/verify_ip_repo.py, core/oauth_crypto.py, core/verify_vpn.py (impronta)
"""

from __future__ import annotations

import logging
from datetime import timedelta

import discord

from core import oauth_crypto
from core.verify_vpn_logic import ip_controllabile

logger = logging.getLogger("iyokai.verify_ip")

MASSIMO_IP_PER_PERSONA = 20
ILLEGGIBILE = "(illeggibile)"
FINESTRA_KICK = timedelta(seconds=30)


def _repo():
    from core.repositories import verify_ip_repo

    return verify_ip_repo.verify_ip_repo


def _chiave_cifratura() -> str:
    from core.config import config

    return config.VERIFY_IP_ENCRYPTION_KEY


def _aad(guild_id: int, user_id: int) -> bytes:
    return f"verify_ip:{guild_id}:{user_id}".encode()


async def salva(guild_id: int, user_id: int, ip: str, esito: str, chiave_impronta: str) -> bool:
    """
    Salva l'IP cifrato. False (e niente in chiaro, da nessuna parte) se manca la chiave, l'IP non è pubblico
    o qualcosa va storto: la verifica non si ferma mai per questo. Il log non dice mai l'IP.
    """
    indirizzo = ip_controllabile(ip)
    chiave = _chiave_cifratura()
    if indirizzo is None or not chiave:
        return False
    from core.verify_vpn import impronta_ip

    try:
        cifrato = oauth_crypto.encrypt_token(str(indirizzo), chiave, aad=_aad(guild_id, user_id))
        await _repo().salva(
            guild_id, user_id, impronta_ip(str(indirizzo), chiave_impronta), cifrato, esito, MASSIMO_IP_PER_PERSONA
        )
    except Exception as errore:  # il messaggio dell'errore potrebbe contenere l'IP: se ne logga solo il tipo
        logger.warning("IP della verifica non salvato nel server %s (%s).", guild_id, type(errore).__name__)
        return False
    return True


async def per_proprietario(bot, user_id: int) -> list[dict]:
    """
    Solo per il proprietario del bot: gli IP della persona con il nome del server. Un IP che non si decifra
    (chiave cambiata) si mostra come illeggibile.
    """
    chiave = _chiave_cifratura()
    voci = []
    for r in await _repo().della_persona(user_id):
        try:
            ip = oauth_crypto.decrypt_token(r["ip_cifrato"], chiave, aad=_aad(r["guild_id"], user_id))
        except Exception:
            ip = ILLEGGIBILE
        server = bot.get_guild(r["guild_id"])
        voci.append({
            "data": r["ultimo_il"].date().isoformat(), "nome": server.name[:60] if server is not None else "?",
            "guild_id": r["guild_id"], "ip": ip, "esito": r["esito"],
        })
    return voci


def righe_per_proprietario(voci: list[dict]) -> list[str]:
    return [f"{v['data']} · **{v['nome']}** (`{v['guild_id']}`) · IP `{v['ip']}` · {v['esito']}" for v in voci]


# ----------------------------------------------------------------- scadenze
async def ha_ip(guild_id: int, user_id: int) -> bool:
    return await _repo().ha_righe(guild_id, user_id)


async def persona_uscita(guild_id: int, user_id: int, *, espulsa: bool) -> None:
    await _repo().persona_uscita(guild_id, user_id, espulsa)


async def persona_tornata(guild_id: int, user_id: int) -> None:
    await _repo().persona_tornata(guild_id, user_id)


async def persona_bannata(guild_id: int, user_id: int) -> None:
    await _repo().persona_bannata(guild_id, user_id)


async def persona_sbloccata(guild_id: int, user_id: int) -> None:
    await _repo().persona_sbloccata(guild_id, user_id)


async def server_uscito(guild_id: int) -> None:
    await _repo().server_uscito(guild_id)


async def server_tornato(guild_id: int) -> None:
    await _repo().server_tornato(guild_id)


async def uscita_con_kick(guild: discord.Guild, user_id: int) -> bool:
    """
    True se il registro di Discord dice che la persona è stata espulsa proprio adesso. Senza il permesso di
    leggere il registro (o con un errore) non si può sapere: l'uscita conta come volontaria (si cancella prima).
    """
    try:
        if not guild.me.guild_permissions.view_audit_log:
            return False
        adesso = discord.utils.utcnow()
        async for voce in guild.audit_logs(limit=5, action=discord.AuditLogAction.kick):
            if getattr(voce.target, "id", None) == user_id and adesso - voce.created_at <= FINESTRA_KICK:
                return True
    except (discord.HTTPException, AttributeError):
        logger.info("Registro di Discord non leggibile nel server %s: l'uscita conta come volontaria.", guild.id)
    return False
