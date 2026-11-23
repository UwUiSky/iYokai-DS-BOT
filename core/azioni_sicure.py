"""
core/azioni_sicure.py
=====================
L'elenco chiuso delle azioni che un tag (UTL-024) o un'azione programmata (UTL-111) possono fare: dare o togliere un
ruolo, scrivere un messaggio, reagire, sbloccare un canale. Mai moderazione né amministrazione, mai un comando
qualsiasi: un tipo fuori elenco non si può nemmeno salvare. Si controllano i permessi di chi usa l'azione (per un tag,
chi lo usa; per una programmata, chi l'ha messa, riletti al momento di eseguire). Menzioni sempre spente.
Funzioni coperte: UTL-024, UTL-111
Dipende da: core/role_safety.py
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import discord

from core.role_safety import check_role_assignable, motivo_ruolo_automatico_non_assegnabile
from core.ticket_logic import looks_like_emoji

TIPI_TAG = ("dai_ruolo", "togli_ruolo", "reazione", "messaggio")  # UTL-024
TIPI_PROGRAMMATE = ("dai_ruolo", "togli_ruolo", "messaggio", "sblocca_canale")  # UTL-111
TIPI = tuple(dict.fromkeys(TIPI_TAG + TIPI_PROGRAMMATE))
MAX_AZIONI_TAG = 3
MAX_PROGRAMMATE = 5  # per server
MAX_TESTO = 200
NESSUNA_MENZIONE = discord.AllowedMentions.none()


class AzioneNonValida(ValueError):
    """L'azione è fuori dall'elenco o le mancano dati."""


@dataclass(frozen=True)
class Azione:
    tipo: str
    ruolo_id: int | None = None
    canale_id: int | None = None
    testo: str | None = None
    emoji: str | None = None
    utente_id: int | None = None


def da_dict(dati: dict, ammessi: tuple[str, ...] = TIPI) -> Azione:
    """Una azione da un dizionario (database o comando). Solleva AzioneNonValida se non è dell'elenco o è incompleta."""
    tipo = dati.get("tipo")
    if tipo not in ammessi:
        raise AzioneNonValida(f"tipo non ammesso: {str(tipo)[:30]}")
    a = Azione(
        tipo=tipo,
        ruolo_id=_intero(dati.get("ruolo_id")),
        canale_id=_intero(dati.get("canale_id")),
        testo=(str(dati["testo"]).strip()[:MAX_TESTO] or None) if dati.get("testo") else None,
        emoji=str(dati["emoji"])[:64] if dati.get("emoji") else None,
        utente_id=_intero(dati.get("utente_id")),
    )
    if tipo in ("dai_ruolo", "togli_ruolo") and a.ruolo_id is None:
        raise AzioneNonValida("serve il ruolo")
    if tipo == "messaggio" and (a.canale_id is None or not a.testo):
        raise AzioneNonValida("servono il canale e il testo")
    if tipo == "reazione" and (a.emoji is None or not looks_like_emoji(a.emoji)):
        raise AzioneNonValida("serve un'emoji")
    if tipo == "sblocca_canale" and a.canale_id is None:
        raise AzioneNonValida("serve il canale")
    return a


def a_dict(azione: Azione) -> dict:
    return {k: v for k, v in asdict(azione).items() if v is not None}


def _intero(valore) -> int | None:
    try:
        return int(valore) if valore is not None else None
    except (TypeError, ValueError):
        return None


async def esegui(
    guild: discord.Guild,
    azione: Azione,
    *,
    esecutore: discord.Member | None,
    bersaglio: discord.Member | None,
    messaggio: discord.Message | None = None,
    autonomo: bool,
) -> str | None:
    """Fa l'azione. Restituisce None se è andata, altrimenti il motivo (per il log o per chi l'ha usata).

    `autonomo` falso = tag: `esecutore` e `bersaglio` sono chi ha usato il tag. `autonomo` vero = azione programmata:
    `esecutore` è chi l'ha messa (permessi riletti ora), `bersaglio` la persona colpita (se serve)."""
    if esecutore is None:
        return "chi ha messo l'azione non è più nel server"
    try:
        if azione.tipo in ("dai_ruolo", "togli_ruolo"):
            return await _ruolo(guild, azione, esecutore, bersaglio, autonomo)
        if azione.tipo == "messaggio":
            canale = guild.get_channel(azione.canale_id or 0)
            if not isinstance(canale, (discord.TextChannel, discord.Thread)):
                return "canale non trovato"
            if not canale.permissions_for(esecutore).send_messages or not canale.permissions_for(guild.me).send_messages:
                return "non si può scrivere in quel canale"
            await canale.send(azione.testo, allowed_mentions=NESSUNA_MENZIONE)
            return None
        if azione.tipo == "reazione":
            if messaggio is None:
                return None  # un comando slash non ha un messaggio: niente da fare, non è un errore
            if not messaggio.channel.permissions_for(esecutore).add_reactions:
                return "non si può reagire qui"
            await messaggio.add_reaction(azione.emoji)
            return None
        if azione.tipo == "sblocca_canale":
            canale = guild.get_channel(azione.canale_id or 0)
            if not isinstance(canale, discord.TextChannel):
                return "canale non trovato"
            if not esecutore.guild_permissions.manage_channels:
                return "serve «Gestire i canali»"
            await canale.set_permissions(guild.default_role, send_messages=None, reason="Azione programmata")
            return None
    except discord.HTTPException:
        return "Discord ha rifiutato l'azione"
    return "tipo non ammesso"


async def _ruolo(guild, azione: Azione, esecutore, bersaglio, autonomo: bool) -> str | None:
    ruolo = guild.get_role(azione.ruolo_id or 0)
    if ruolo is None or bersaglio is None:
        return "ruolo o persona non trovati"
    if autonomo:
        if not esecutore.guild_permissions.manage_roles:
            return "serve «Gestire i ruoli»"
        motivo = check_role_assignable(guild, ruolo, esecutore, self_service=False)
    else:
        motivo = motivo_ruolo_automatico_non_assegnabile(guild, ruolo.id)
    if motivo is not None:
        return motivo
    if azione.tipo == "dai_ruolo":
        await bersaglio.add_roles(ruolo, reason="Azione sicura")
    else:
        await bersaglio.remove_roles(ruolo, reason="Azione sicura")
    return None
