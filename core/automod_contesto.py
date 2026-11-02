"""
core/automod_contesto.py
========================
Costruisce il `Contesto` delle regole AutoMod da un messaggio (o da un membro): legge solo attributi, non
chiama Discord. Il bot, i suoi worker e i suoi webhook risultano «propri» e non vengono mai giudicati.
Funzioni coperte: SPEC §6 (AMD-029, 032-040), D63
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from core.automod_regole_logic import Contesto, Regola


def _int(valore: Any) -> int | None:
    return valore if isinstance(valore, int) and not isinstance(valore, bool) else None


def _giorni(da: Any, adesso: datetime) -> int | None:
    return max(0, (adesso - da).days) if isinstance(da, datetime) else None


def _posto_del_canale(canale: Any) -> tuple[int | None, int | None, bool]:
    """(categoria, canale padre se thread, è un thread)."""
    padre_id = _int(getattr(canale, "parent_id", None))
    if padre_id is not None and hasattr(canale, "owner_id"):  # Thread
        padre = getattr(canale, "parent", None)
        return _int(getattr(padre, "category_id", None)), padre_id, True
    return _int(getattr(canale, "category_id", None)), None, False


def e_proprio(autore_id: int, webhook_id: int | None, application_id: int | None, *, nostro_bot, id_applicazione: int | None) -> bool:
    """True per il bot, per Mod e per i webhook creati dalla nostra applicazione."""
    if nostro_bot(autore_id):
        return True
    return webhook_id is not None and application_id is not None and application_id == id_applicazione


def contesto_da_messaggio(
    message: Any, *, nostro_bot, id_applicazione: int | None = None, livello: int | None = None,
    evento: str = "messaggio", adesso: datetime | None = None,
) -> Contesto:
    adesso = adesso or datetime.now(timezone.utc)
    autore = message.author
    guild_id = message.guild.id
    categoria, padre, in_thread = _posto_del_canale(message.channel)
    ruoli = frozenset(r.id for r in getattr(autore, "roles", ()) if r.id != guild_id)
    webhook = _int(getattr(message, "webhook_id", None))
    return Contesto(
        evento=evento,
        autore_id=autore.id,
        ruoli_ids=ruoli,
        e_bot=bool(getattr(autore, "bot", False)) or webhook is not None,
        e_webhook=webhook is not None,
        e_proprio=e_proprio(autore.id, webhook, _int(getattr(message, "application_id", None)),
                            nostro_bot=nostro_bot, id_applicazione=id_applicazione),
        eta_account_giorni=_giorni(getattr(autore, "created_at", None), adesso),
        nel_server_giorni=_giorni(getattr(autore, "joined_at", None), adesso),
        livello=livello,
        canale_id=message.channel.id,
        categoria_id=categoria,
        thread_padre_id=padre,
        in_thread=in_thread,
        ora=adesso,
    )


def serve_il_livello(regole: tuple[Regola, ...]) -> bool:
    """Il livello si legge dal database solo se una regola attiva lo chiede."""
    return any(r.attiva and r.condizioni.livello != (None, None) for r in regole)


def serve_chi_non_e_persona(regole: tuple[Regola, ...]) -> bool:
    return any(r.attiva and set(r.condizioni.autori) != {"persone"} for r in regole)


def contesto_da_membro(membro: Any, canale: Any, *, evento: str = "messaggio", adesso: datetime | None = None) -> Contesto:
    """Il contesto di un membro in un canale, per «Prova» nel pannello: non serve un messaggio vero."""
    adesso = adesso or datetime.now(timezone.utc)
    categoria, padre, in_thread = _posto_del_canale(canale)
    return Contesto(
        evento=evento, autore_id=membro.id,
        ruoli_ids=frozenset(r.id for r in getattr(membro, "roles", ()) if r.id != membro.guild.id),
        e_bot=bool(getattr(membro, "bot", False)),
        eta_account_giorni=_giorni(getattr(membro, "created_at", None), adesso),
        nel_server_giorni=_giorni(getattr(membro, "joined_at", None), adesso),
        canale_id=_int(getattr(canale, "id", None)), categoria_id=categoria, thread_padre_id=padre, in_thread=in_thread,
        ora=adesso,
    )
