"""
core/backup_pulizia_logic.py
============================
Cancellazione facoltativa di canali e ruoli già presenti, prima di caricare
una struttura (BKP-004, D133). Spenta di base, solo per il proprietario del
server. Non tocca mai: ruoli gestiti, @everyone, ruoli pari o sopra il bot,
il canale in cui si lavora (e il suo genitore), canali richiesti dalla community.
Funzioni coperte: BKP-004, M 12.17
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Awaitable, Callable

import discord

MAX_MOTIVO = 512
GRUPPO = 5  # cancellazioni tra una pausa e l'altra
PAUSA = 1.0

Avanzamento = Callable[[str, int, int], Awaitable[bool]]


async def _niente(_passo: str, _fatti: int, _totale: int) -> bool:
    return False


def motivo_audit(autore_id: int) -> str:
    """Il motivo nel registro di Discord (≤ 512)."""
    return f"Pulizia prima del caricamento backup iYokai, chiesta dal proprietario {autore_id}"[:MAX_MOTIVO]


@dataclass
class Piano:
    canali: list = field(default_factory=list)
    ruoli: list = field(default_factory=list)
    risparmiati: dict[str, int] = field(default_factory=dict)

    @property
    def totale(self) -> int:
        return len(self.canali) + len(self.ruoli)


def pianifica(guild, canale_id: int | None, genitore_id: int | None, canali: bool, ruoli: bool) -> Piano:
    """Cosa verrebbe cancellato adesso e cosa si risparmia (con il motivo)."""
    piano = Piano()

    def risparmia(motivo: str) -> None:
        piano.risparmiati[motivo] = piano.risparmiati.get(motivo, 0) + 1

    if canali:
        protetti = {canale_id, genitore_id}
        for nome in ("rules_channel", "public_updates_channel", "safety_alerts_channel"):
            speciale = getattr(guild, nome, None)
            if speciale is not None:
                protetti.add(speciale.id)
        for canale in guild.channels:
            if canale.id in (canale_id, genitore_id):
                risparmia("canale in cui lavori")
            elif canale.id in protetti:
                risparmia("canale richiesto dalla community")
            else:
                piano.canali.append(canale)
    if ruoli:
        io = getattr(guild, "me", None)
        massimo = getattr(io, "top_role", None)
        for ruolo in guild.roles:
            if ruolo.is_default():
                continue  # @everyone non conta: non si cancella e non si elenca
            if ruolo.managed:
                risparmia("ruolo gestito (bot, booster, integrazioni)")
            elif massimo is None or ruolo >= massimo:
                risparmia("ruolo pari o sopra il bot")
            else:
                piano.ruoli.append(ruolo)
    return piano


def riepilogo_prima(piano: Piano) -> str:
    """Il testo del passo di conferma: quanti, e cosa resta."""
    righe = [f"🗑️ Verranno cancellati **{len(piano.canali)}** canali e **{len(piano.ruoli)}** ruoli."]
    righe += [f"• Non toccati ({n}): {m}" for m, n in piano.risparmiati.items()]
    return "\n".join(righe)


class PuliziaNegata(Exception):
    """Chi chiede non è (più) il proprietario del server."""


@dataclass
class RiepilogoPulizia:
    canali: int = 0
    ruoli: int = 0
    saltati: int = 0
    interrotta: bool = False
    note: list[str] = field(default_factory=list)

    def testo(self) -> str:
        righe = [f"🗑️ Cancellati: {self.canali} canali, {self.ruoli} ruoli. Saltati: {self.saltati}."]
        righe += [f"• {n}" for n in self.note[:10]]
        return "\n".join(righe)[:1500]


async def esegui(
    guild, autore_id: int, canale_id: int | None, genitore_id: int | None, canali: bool, ruoli: bool,
    avanza: Avanzamento = _niente, pausa: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> RiepilogoPulizia:
    """
    Cancella a gruppi, con pause. Il proprietario si ricontrolla qui e il piano si ricalcola.
    Se un passo fallisce per un motivo diverso da «non si può» o si chiede di annullare, si ferma:
    `interrotta` è True e chi chiama NON carica.
    """
    if autore_id != guild.owner_id:
        raise PuliziaNegata
    piano = pianifica(guild, canale_id, genitore_id, canali, ruoli)
    r = RiepilogoPulizia(saltati=sum(piano.risparmiati.values()))
    r.note += [f"{m}: {n} non toccati" for m, n in piano.risparmiati.items()]
    motivo = motivo_audit(autore_id)
    fatti = 0
    for tipo, elementi in (("canali", piano.canali), ("ruoli", piano.ruoli)):
        for elemento in elementi:
            fatti += 1
            if await avanza(f"cancella {tipo}", fatti, piano.totale):
                r.interrotta = True
                r.note.append("Cancellazione annullata.")
                return r
            try:
                await elemento.delete(reason=motivo)
                if tipo == "canali":
                    r.canali += 1
                else:
                    r.ruoli += 1
            except discord.NotFound:
                pass  # già sparito
            except discord.Forbidden:
                r.saltati += 1
                r.note.append("Discord non permette di cancellarne alcuni: saltati")
            except discord.HTTPException as errore:
                if errore.status == 400:  # es. canali richiesti dalla community
                    r.saltati += 1
                    r.note.append("Discord non permette di cancellarne alcuni: saltati")
                    continue
                r.interrotta = True
                r.note.append(f"Cancellazione interrotta da Discord (errore {errore.status}).")
                return r
            if fatti % GRUPPO == 0:
                await pausa(PAUSA)
    return r
