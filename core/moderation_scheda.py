"""
core/moderation_scheda.py
=========================
La scheda di moderazione di un utente (date, casi attivi contati, ultimi casi, note, rischio) e l'elenco dei suoi
casi visibili a lui stesso (`/utility mie-sanzioni`). Funzioni che costruiscono testi e riquadri, senza Discord
vivo: i comandi e i menu col tasto destro le chiamano. Un riquadro tiene al massimo 25 campi e 6.000 caratteri.
Funzioni coperte: SPEC §5.7 (MOD-106, MOD-114, MOD-115)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import discord

from core.repositories.moderation_repo import ModerationCase, moderation_repo

MAX_ULTIMI = 5
MAX_MIE = 10
MAX_CAMPO = 1024
MAX_MOTIVO_RIGA = 80
MAX_NOTA = 200


@dataclass(frozen=True)
class DatiScheda:
    user_id: int
    nome: str
    creato: datetime
    entrato: datetime | None  # None = non è nel server
    conteggi: dict[str, tuple[int, int]]  # tipo -> (attivi, totali)
    ultimi: list[ModerationCase]
    note: int
    rischio: str | None


def riga_caso(caso: ModerationCase, moderatore: str | None = None) -> str:
    """«#12 warn — 03/11/2026 — motivo…»; con un moderatore da nominare in fondo."""
    motivo = (caso.reason or "-").replace("\n", " ")
    if len(motivo) > MAX_MOTIVO_RIGA:
        motivo = motivo[: MAX_MOTIVO_RIGA - 1] + "…"
    stato = "" if caso.active else " (chiuso)"
    riga = f"#{caso.case_number} {caso.action_type}{stato} — {discord.utils.format_dt(caso.created_at, 'd')} — {motivo}"
    if moderatore:
        riga += f" — {moderatore}"
    return riga


def _tronca(testo: str) -> str:
    return testo if len(testo) <= MAX_CAMPO else testo[: MAX_CAMPO - 1] + "…"


async def leggi_scheda(guild_id: int, utente: discord.abc.User, membro: discord.Member | None, rischio: str | None) -> DatiScheda:
    """Legge dal database i dati della scheda. `membro` è None se l'utente non è nel server."""
    return DatiScheda(
        user_id=utente.id,
        nome=getattr(membro or utente, "display_name", None) or utente.name,
        creato=utente.created_at,
        entrato=membro.joined_at if membro is not None else None,
        conteggi=await moderation_repo.count_cases_by_type(guild_id, utente.id),
        ultimi=await moderation_repo.list_visible_cases_for_user(guild_id, utente.id, MAX_ULTIMI),
        note=await moderation_repo.count_notes_for_user(guild_id, utente.id),
        rischio=rischio,
    )


def embed_scheda(dati: DatiScheda, t: dict[str, str]) -> discord.Embed:
    """Il riquadro. `t` ha i testi già tradotti: titolo, account, entrato, fuori, attivi, nessuno, totali, ultimi, note, rischio."""
    embed = discord.Embed(title=t["titolo"].format(nome=dati.nome)[:256], color=discord.Color.blurple())
    embed.add_field(name=t["account"], value=discord.utils.format_dt(dati.creato, "D"), inline=True)
    embed.add_field(
        name=t["entrato"], value=discord.utils.format_dt(dati.entrato, "D") if dati.entrato else t["fuori"], inline=True
    )
    attivi = ", ".join(f"{tipo} {a}" for tipo, (a, _) in sorted(dati.conteggi.items()) if a) or t["nessuno"]
    embed.add_field(name=t["attivi"], value=_tronca(attivi), inline=False)
    embed.add_field(name=t["totali"], value=str(sum(tot for _, tot in dati.conteggi.values())), inline=True)
    embed.add_field(name=t["note"], value=str(dati.note), inline=True)
    if dati.ultimi:
        embed.add_field(name=t["ultimi"], value=_tronca("\n".join(riga_caso(c) for c in dati.ultimi)), inline=False)
    if dati.rischio:
        embed.add_field(name=t["rischio"], value=_tronca(dati.rischio), inline=False)
    return embed


def righe_mie_sanzioni(casi: list[ModerationCase], staff_di: str | None, moderatori: dict[int, str]) -> str:
    """L'elenco dei casi per `/utility mie-sanzioni`: mai le note. Con `staff_di` («Staff di <server>») il moderatore non si nomina."""
    righe = []
    for c in casi[:MAX_MIE]:
        righe.append(riga_caso(c, moderatore=staff_di or moderatori.get(c.moderator_id, "-")))
    return "\n".join(righe)
