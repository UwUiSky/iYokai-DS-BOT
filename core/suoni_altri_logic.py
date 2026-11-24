"""
core/suoni_altri_logic.py
=========================
Suoni delle soundboard di altri server (D127, D129): quali si possono proporre, come si descrive il server
d'origine, pausa e tetto orario per persona. Logica pura, niente Discord.
Funzioni coperte: SPEC §23 (FUN-075)
Dipende da: niente
"""

from __future__ import annotations

import time
from collections.abc import Iterable
from dataclasses import dataclass

MAX_VOCI_MENU = 25  # tetto del menu a tendina di Discord
MAX_CERCA = 50
PAUSA_ESTERNI = 15.0  # secondi tra due suoni (o anteprime) della stessa persona
MAX_ESTERNI_ORA = 12  # per persona, in tutti i server insieme
MAX_PERSONE_RICORDATE = 5000
FUNZIONE_PUBBLICA = "DISCOVERABLE"  # il server compare nella ricerca pubblica di Discord


@dataclass(frozen=True)
class SuonoAltro:
    """Un suono della soundboard di un altro server, letto dalla cache di Discord."""

    id: int
    nome: str
    emoji: str | None
    guild_id: int
    guild_nome: str
    pubblico: bool

    @property
    def valore(self) -> str:
        """Valore dell'opzione del menu: server e suono (un id di suono è unico, il server serve al controllo)."""
        return f"{self.guild_id}:{self.id}"

    @property
    def etichetta(self) -> str:
        return (f"{self.emoji} {self.nome}" if self.emoji else self.nome)[:100]

    def origine(self) -> str | None:
        """Il nome del server d'origine solo se è pubblico; altrimenti niente (non si rivela un server privato)."""
        return self.guild_nome[:100] if self.pubblico and self.guild_nome else None


def server_pubblico(funzioni: Iterable[str]) -> bool:
    return FUNZIONE_PUBBLICA in set(funzioni or ())


def candidati(suoni: Iterable[SuonoAltro], guild_id: int, condivisi: set[int], cerca: str = "") -> list[SuonoAltro]:
    """I suoni proponibili in `guild_id`: di altri server che li hanno messi a disposizione, per nome, al massimo 25."""
    chiave = (cerca or "").strip().casefold()[:MAX_CERCA]
    scelti = [s for s in suoni if s.guild_id != guild_id and s.guild_id in condivisi and chiave in s.nome.casefold()]
    scelti.sort(key=lambda s: (s.nome.casefold(), s.guild_id, s.id))
    return scelti[:MAX_VOCI_MENU]


def trova(suoni: Iterable[SuonoAltro], valore: str) -> SuonoAltro | None:
    return next((s for s in suoni if s.valore == (valore or "").strip()), None)


class TettoPersona:
    """Pausa tra due usi e tetto orario per persona, in tutti i server (i suoni degli altri si pagano in attenzione)."""

    def __init__(self, pausa: float = PAUSA_ESTERNI, massimo: int = MAX_ESTERNI_ORA, orologio=time.monotonic) -> None:
        self._pausa = pausa
        self._massimo = massimo
        self._orologio = orologio
        self._usi: dict[int, list[float]] = {}

    def _recenti(self, user_id: int) -> list[float]:
        adesso = self._orologio()
        return [t for t in self._usi.get(user_id, []) if adesso - t < 3600]

    def controlla(self, user_id: int) -> tuple[str, float] | None:
        """None se si può; altrimenti ("pausa", secondi) o ("ora", secondi alla scadenza del tetto)."""
        recenti = self._recenti(user_id)
        if not recenti:
            return None
        adesso = self._orologio()
        da_ultimo = adesso - recenti[-1]
        if da_ultimo < self._pausa:
            return "pausa", self._pausa - da_ultimo
        if len(recenti) >= self._massimo:
            return "ora", 3600 - (adesso - recenti[0])
        return None

    def segna(self, user_id: int) -> None:
        recenti = self._recenti(user_id)
        recenti.append(self._orologio())
        self._usi[user_id] = recenti[-self._massimo:]
        if len(self._usi) > MAX_PERSONE_RICORDATE:  # niente crescita senza fine
            adesso = self._orologio()
            self._usi = {u: v for u, v in self._usi.items() if v and adesso - v[-1] < 3600}
