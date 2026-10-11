"""
core/snipe_logic.py
=======================
Logica pura per Snipe ed Editsnipe (SPEC.md §14.9, §14.10), Reactionsnipe
(§14.11) e Ghost ping detection (§14.12) — solo stringhe, numeri e date,
niente discord.py.

Snipe ed Editsnipe mostrano il testo del messaggio: servono il Message
Content Intent (acceso, D9). Restano in memoria per pochi minuti e non
vengono mai scritti su disco. Reactionsnipe e Ghost ping non leggono il
testo: usano emoji, autore e l'elenco dei membri menzionati, che Discord
manda sempre.
Funzioni coperte: SPEC §14.9-§14.12 (NF-03, M 5.9)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

SNIPE_TTL_SECONDS = 5 * 60
DESCRIZIONE_MAX = 4096
# Una cancellazione di un moderatore scrive una voce nel registro proprio mentre
# arriva l'evento: una voce più vecchia di così non riguarda questo messaggio.
TOLLERANZA_REGISTRO_SECONDI = 3
PER_SERVER_MAX = 50
TOTALE_MAX = 20_000
POTATURA_OGNI = 500


def scaduto(creato: datetime, adesso: datetime, ttl: int = SNIPE_TTL_SECONDS) -> bool:
    """True se il messaggio ricordato ha più di `ttl` secondi."""
    return (adesso - creato).total_seconds() > ttl


def testo_snipe(content: str, nomi_allegati: list[str]) -> str:
    """Il testo da mostrare: contenuto (tagliato a 4096) e allegati; mai vuoto."""
    parti = [content] if content else []
    if nomi_allegati:
        parti.append("📎 " + ", ".join(nomi_allegati))
    testo = "\n".join(parti) or "*(nessun testo)*"
    if len(testo) > DESCRIZIONE_MAX:
        testo = testo[: DESCRIZIONE_MAX - 1] + "…"
    return testo


@dataclass(frozen=True)
class VoceRegistro:
    """Una voce «messaggio cancellato» del registro di controllo di Discord."""

    entry_id: int
    user_id: int | None  # chi ha cancellato
    target_id: int | None  # di chi era il messaggio
    channel_id: int | None
    count: int  # Discord unisce più cancellazioni uguali in una voce sola
    created_ts: float


def cancellato_da_altri(
    voci: list[VoceRegistro],
    author_id: int,
    channel_id: int,
    visti: dict[int, int],
    evento_ts: float,
) -> bool:
    """
    True se questa cancellazione (ricevuta a `evento_ts`) è opera di qualcun altro.
    Vale una voce dell'autore in quel canale, di un altro utente, che o è nuova
    (creata attorno all'evento) o, se già vista, ha il conteggio salito.
    `visti` (id voce -> conteggio) si aggiorna qui e va conservato tra le chiamate.
    """
    trovato = False
    for v in voci:
        if v.user_id is None or v.user_id == author_id:
            continue
        if v.target_id != author_id or v.channel_id != channel_id:
            continue
        if v.entry_id in visti:
            nuova = v.count > visti[v.entry_id]
        else:
            nuova = v.created_ts >= evento_ts - TOLLERANZA_REGISTRO_SECONDI
        visti[v.entry_id] = v.count
        trovato = trovato or nuova
    return trovato


class RicordiSnipe:
    """
    L'ultima voce per canale, solo in memoria. Scade dopo `ttl` secondi anche
    in scrittura (potatura), e ogni server ne tiene al più `per_server`, così
    un server non fa uscire i canali degli altri.
    """

    def __init__(self, ttl: int = SNIPE_TTL_SECONDS, per_server: int = PER_SERVER_MAX) -> None:
        self._ttl = ttl
        self._per_server = per_server
        self._voci: dict[int, object] = {}  # canale -> voce (con .guild_id e .quando)
        self._dei_server: dict[int, dict[int, None]] = {}  # server -> canali, dal più vecchio
        self._scritture = 0

    def __len__(self) -> int:
        return len(self._voci)

    def _scaduta(self, voce) -> bool:
        return scaduto(voce.quando, datetime.now(timezone.utc), self._ttl)

    def _togli(self, channel_id: int) -> None:
        voce = self._voci.pop(channel_id, None)
        if voce is not None:
            self._dei_server.get(voce.guild_id, {}).pop(channel_id, None)

    def get(self, channel_id: int):
        voce = self._voci.get(channel_id)
        if voce is not None and self._scaduta(voce):
            self._togli(channel_id)
            return None
        return voce

    def delete(self, channel_id: int) -> None:
        self._togli(channel_id)

    def _pota(self, channels: list[int]) -> None:
        for c in channels:
            voce = self._voci.get(c)
            if voce is not None and self._scaduta(voce):
                self._togli(c)

    def set(self, channel_id: int, voce) -> None:
        self._togli(channel_id)
        canali = self._dei_server.setdefault(voce.guild_id, {})
        self._pota(list(canali))
        canali[channel_id] = None
        self._voci[channel_id] = voce
        while len(canali) > self._per_server:
            self._togli(next(iter(canali)))
        self._scritture += 1
        if self._scritture % POTATURA_OGNI == 0:
            self._pota(list(self._voci))
        while len(self._voci) > TOTALE_MAX:
            self._togli(next(iter(self._voci)))


def is_ghost_ping_candidate(
    mentioned_user_ids: list[int], mentions_everyone: bool, author_is_bot: bool
) -> bool:
    """
    Un messaggio va tracciato per il ghost ping se menziona almeno
    un utente (o @everyone/@here) e non è stato scritto da un bot
    (i messaggi automatici del bot stesso, o di altri bot, non
    contano come "ghost ping" di un membro).
    """
    if author_is_bot:
        return False
    return bool(mentioned_user_ids) or mentions_everyone
