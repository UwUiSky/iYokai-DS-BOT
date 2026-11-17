"""
core/live_role_logic.py
=======================
Dà e toglie il ruolo «in diretta». Due strade: chi è collegato a un avviso Twitch, Kick o Picarto
(NF-32, scelto con /admin-moduli alert ruolo-live, senza l'intent delle presenze) e chi risulta «in diretta» per
Discord, con le regole di /admin-alert ruolo-live (#129 ALR-042..048: solo certi ruoli, esclusi, parole o giochi,
eccezioni, annuncio, fino a 5 regole; serve l'intent delle presenze).
Funzioni coperte: SPEC §10.13 (NF-32, #129 ALR-042, 043, 044, 045, 046, 047, 048)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from urllib.parse import urlsplit

import discord

from core.alert_messaggio_logic import pulisci_esterno
from core.alert_options_logic import parse_parole
from core.template_renderer import render_template

logger = logging.getLogger("iyokai.live_role")


async def aggiorna_ruolo_live(guild, member_id: int | None, role_id: int | None, in_diretta: bool) -> bool:
    """True se il ruolo è stato cambiato. Mai un'eccezione: un ruolo che non si può dare non ferma l'avviso."""
    if not member_id or not role_id or guild is None:
        return False
    membro = guild.get_member(member_id)
    ruolo = guild.get_role(role_id)
    me = guild.me
    if membro is None or ruolo is None or me is None or membro.bot:
        return False
    if not me.guild_permissions.manage_roles or ruolo >= me.top_role or ruolo.managed:
        return False
    ce_l_ha = ruolo in membro.roles
    try:
        if in_diretta and not ce_l_ha:
            await membro.add_roles(ruolo, reason="In diretta")
            return True
        if not in_diretta and ce_l_ha:
            await membro.remove_roles(ruolo, reason="Diretta finita")
            return True
    except discord.HTTPException:
        logger.warning("Ruolo in diretta non aggiornato (server %s, membro %s)", guild.id, member_id)
    return False


# ------------------------------------------------------------------ ruolo «in diretta» per attività di Discord (ALR-042..048)
HOST_DIRETTE = ("twitch.tv", "youtube.com", "youtu.be", "kick.com", "picarto.tv")
MODELLO_ANNUNCIO = "🔴 {utente} è in diretta: {titolo}\n{link}"
MAX_MODELLO_ANNUNCIO = 300
_ultimi_annunci: dict[tuple[int, int], datetime] = {}
MAX_MEMORIA_ANNUNCI = 5000


@dataclass(frozen=True)
class Diretta:
    titolo: str
    gioco: str
    url: str


def indirizzo_diretta(url: str | None) -> str:
    """L'indirizzo dell'attività se punta a un sito di dirette noto (https); altrimenti vuoto."""
    if not url or len(url) > 300:
        return ""
    p = urlsplit(url)
    host = (p.hostname or "").lower()
    ok = p.scheme == "https" and not p.username and any(host == h or host.endswith("." + h) for h in HOST_DIRETTE)
    return url if ok else ""


def diretta_da_attivita(attivita) -> Diretta | None:
    """La prima attività «Streaming» di un membro (titolo, gioco e link già puliti); None se non è in diretta."""
    for a in attivita or ():
        if isinstance(a, discord.Streaming):
            return Diretta(pulisci_esterno(a.name, 200), pulisci_esterno(getattr(a, "game", None), 100), indirizzo_diretta(a.url))
    return None


def regola_ammette(regola, membro_id: int, ruoli_ids: set[int], diretta: Diretta) -> bool:
    """Se la regola dà il ruolo a questo membro in diretta. Gli esclusi vincono su tutto; le eccezioni saltano solo
    i filtri su parole e gioco (non il ruolo richiesto)."""
    if membro_id in regola.esclusi_membri or ruoli_ids & regola.esclusi_ruoli:
        return False
    if regola.only_role_id and regola.only_role_id not in ruoli_ids:
        return False
    if membro_id in regola.eccezioni:
        return True
    parole = parse_parole(regola.keywords)
    titolo = diretta.titolo.lower()
    escluse = [p[1:].strip() for p in parole if p.startswith("-")]
    ammesse = [p for p in parole if not p.startswith("-")]
    if any(e and e in titolo for e in escluse) or (ammesse and not any(a in titolo for a in ammesse)):
        return False
    giochi = parse_parole(regola.games)
    return not giochi or diretta.gioco.strip().lower() in giochi


async def _cambia_ruolo(guild, membro, ruolo_id: int, dare: bool) -> bool:
    return await aggiorna_ruolo_live(guild, membro.id, ruolo_id, dare)


def testo_annuncio(regola, membro, diretta: Diretta) -> str:
    modello = (regola.announce_template or MODELLO_ANNUNCIO)[:MAX_MODELLO_ANNUNCIO]
    return render_template(modello, {
        "utente": pulisci_esterno(getattr(membro, "display_name", ""), 50), "titolo": diretta.titolo or "-",
        "gioco": diretta.gioco, "link": diretta.url,
    })[:1000]


async def annuncia(guild, membro, regola, diretta: Diretta, adesso: datetime) -> bool:
    """Un annuncio nel canale scelto, con pausa per membro e per regola. True se è stato mandato."""
    if not regola.announce_channel_id:
        return False
    chiave = (regola.id, membro.id)
    ultimo = _ultimi_annunci.get(chiave)
    if ultimo and adesso - ultimo < timedelta(minutes=max(regola.announce_gap_minutes, 1)):
        return False
    canale = guild.get_channel(regola.announce_channel_id)
    me = guild.me
    if not isinstance(canale, discord.TextChannel) or me is None or not canale.permissions_for(me).send_messages:
        return False
    if len(_ultimi_annunci) >= MAX_MEMORIA_ANNUNCI:
        _ultimi_annunci.clear()
    _ultimi_annunci[chiave] = adesso
    try:
        await canale.send(testo_annuncio(regola, membro, diretta), allowed_mentions=discord.AllowedMentions.none())
    except discord.HTTPException:
        logger.warning("Annuncio «in diretta» non inviato (server %s)", guild.id)
        return False
    return True


async def applica_regole(guild, membro, regole: list, diretta: Diretta | None, adesso: datetime) -> None:
    """Dà o toglie i ruoli delle regole in base allo stato «in diretta» del membro. Mai un'eccezione."""
    if membro.bot:
        return
    ruoli_ids = {r.id for r in membro.roles}
    for regola in regole:
        ha_ruolo = regola.role_id in ruoli_ids
        vuole = diretta is not None and regola_ammette(regola, membro.id, ruoli_ids, diretta)
        if vuole and not ha_ruolo:
            if await _cambia_ruolo(guild, membro, regola.role_id, True):
                await annuncia(guild, membro, regola, diretta, adesso)
        elif not vuole and ha_ruolo:
            await _cambia_ruolo(guild, membro, regola.role_id, False)


def _azzera_annunci_per_test() -> None:
    _ultimi_annunci.clear()
