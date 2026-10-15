"""
core/music_request_logic.py
===========================
Canale delle richieste musicali: stato del player, testo del messaggio
"player", ripetizione a giro, pausa minima tra due aggiornamenti.
Funzioni coperte: SPEC §23 (NF-19), M 8.19
Dipende da: niente di Discord o Lavalink (logica pura, provabile da sola).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from core.music_logic import build_progress_bar, format_duration, truncate_title

# LIM-21 e Parte 4: titolo dell'embed 256, descrizione 4096, campo 1024.
TITOLO_MAX = 256
CAMPO_MAX = 1024
PROSSIMI_MOSTRATI = 5

# Pausa minima tra due modifiche del messaggio player (limite della scheda).
PAUSA_AGGIORNAMENTO = 5.0

# Testo scritto nel canale: stessa lunghezza massima di una query di play.
QUERY_MAX = 300
# Pausa minima tra due richieste scritte dallo stesso utente (ogni richiesta
# e' una ricerca su Lavalink, una cancellazione e una risposta).
PAUSA_RICHIESTE = 3.0

MODO_NORMALE = "normale"
MODO_TRACCIA = "traccia"
MODO_CODA = "coda"
# Ordine del bottone "ripeti": normale -> traccia -> coda -> normale.
_GIRO_RIPETI = {MODO_NORMALE: MODO_TRACCIA, MODO_TRACCIA: MODO_CODA, MODO_CODA: MODO_NORMALE}
ETICHETTA_MODO = {
    MODO_NORMALE: "spenta",
    MODO_TRACCIA: "🔂 brano",
    MODO_CODA: "🔁 coda",
}


def prossimo_modo_ripeti(modo: str) -> str:
    """Il modo dopo un clic su "ripeti"."""
    return _GIRO_RIPETI.get(modo, MODO_NORMALE)


@dataclass(frozen=True)
class StatoPlayer:
    """Ciò che serve al messaggio player, letto dal player wavelink."""

    titolo: str | None = None
    autore: str | None = None
    durata_ms: int = 0
    posizione_ms: int = 0
    in_pausa: bool = False
    modo: str = MODO_NORMALE
    prossimi: tuple[str, ...] = field(default_factory=tuple)
    in_coda: int = 0
    canale_vocale: str | None = None


def contenuto_player(stato: StatoPlayer | None) -> dict:
    """
    Titolo, descrizione e campi dell'embed del player, entro i limiti di
    Discord. Senza stato (nessuna sessione) il player dice come si usa.
    """
    if stato is None or stato.titolo is None:
        return {
            "titolo": "🎵 Nessun brano in riproduzione",
            "descrizione": (
                "Entra in un canale vocale e scrivi qui il titolo di un brano o un link: "
                "finisce in coda. Puoi anche allegare un file audio."
            ),
            "campi": [],
        }
    stato_testo = "⏸️ In pausa" if stato.in_pausa else "▶️ In riproduzione"
    barra = build_progress_bar(stato.posizione_ms, stato.durata_ms) if stato.durata_ms else ""
    descrizione = f"{stato_testo}"
    if stato.autore:
        descrizione += f" · {truncate_title(stato.autore, 100)}"
    if barra:
        descrizione += (
            f"\n{barra} {format_duration(stato.posizione_ms)} / {format_duration(stato.durata_ms)}"
        )
    righe = [
        f"{i}. {truncate_title(t, 150)}" for i, t in enumerate(stato.prossimi[:PROSSIMI_MOSTRATI], 1)
    ]
    altri = stato.in_coda - len(righe)
    if altri > 0:
        righe.append(f"… e altri {altri}")
    campi = [
        ("In coda", truncate_title("\n".join(righe) or "Coda vuota", CAMPO_MAX)),
        ("Ripetizione", ETICHETTA_MODO.get(stato.modo, ETICHETTA_MODO[MODO_NORMALE])),
    ]
    if stato.canale_vocale:
        campi.append(("Canale", truncate_title(stato.canale_vocale, 100)))
    return {
        "titolo": truncate_title(f"🎶 {stato.titolo}", TITOLO_MAX),
        "descrizione": descrizione,
        "campi": campi,
    }


def modo_da_player(modo_coda) -> str:
    """Da wavelink.QueueMode (letto per nome) al modo del player."""
    nome = getattr(modo_coda, "name", str(modo_coda))
    return {"loop": MODO_TRACCIA, "loop_all": MODO_CODA}.get(nome, MODO_NORMALE)


def stato_da_player(player) -> StatoPlayer | None:
    """Lo stato mostrato dal messaggio, letto da un player wavelink (o None)."""
    corrente = getattr(player, "current", None) if player is not None else None
    if corrente is None:
        return None
    coda = list(getattr(player, "queue", []) or [])
    canale = getattr(player, "channel", None)
    return StatoPlayer(
        titolo=str(getattr(corrente, "title", "") or "Senza titolo"),
        autore=getattr(corrente, "author", None),
        durata_ms=int(getattr(corrente, "length", 0) or 0),
        posizione_ms=int(getattr(player, "position", 0) or 0),
        in_pausa=bool(getattr(player, "paused", False)),
        modo=modo_da_player(getattr(getattr(player, "queue", None), "mode", None)),
        prossimi=tuple(str(getattr(t, "title", "")) for t in coda[:PROSSIMI_MOSTRATI]),
        in_coda=len(coda),
        canale_vocale=getattr(canale, "name", None),
    )


def query_da_messaggio(testo: str, allegati: list[tuple[str, str | None]]) -> str | None:
    """
    Che cosa mettere in coda da un messaggio del canale: il testo (tagliato
    a QUERY_MAX) o, se manca, il primo allegato audio o video (MUS-009).
    `allegati` = coppie (url, content_type). None se non c'è nulla.
    """
    testo = (testo or "").strip()
    if testo:
        return testo[:QUERY_MAX]
    for url, tipo in allegati:
        if allegato_audio(tipo):
            return url
    return None


def allegato_audio(content_type: str | None) -> bool:
    """MUS-009: solo file audio o video (Lavalink ne legge la traccia audio)."""
    tipo = (content_type or "").split(";")[0].strip().lower()
    return tipo.startswith("audio/") or tipo.startswith("video/")


class PausaAggiornamenti:
    """
    Al massimo un aggiornamento del messaggio ogni PAUSA_AGGIORNAMENTO
    secondi per server. `attesa(guild_id)` dice quanto aspettare (0 = subito).
    """

    def __init__(self, pausa: float = PAUSA_AGGIORNAMENTO, orologio=time.monotonic) -> None:
        self._pausa = pausa
        self._orologio = orologio
        self._ultimo: dict[int, float] = {}

    def attesa(self, guild_id: int) -> float:
        ultimo = self._ultimo.get(guild_id)
        if ultimo is None:
            return 0.0
        return max(0.0, self._pausa - (self._orologio() - ultimo))

    def segna(self, guild_id: int) -> None:
        self._ultimo[guild_id] = self._orologio()

    def dimentica(self, guild_id: int) -> None:
        self._ultimo.pop(guild_id, None)
