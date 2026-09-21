"""
core/main_radio_logic.py
============================
Logica pura della radio condivisa del bot principale (SPEC.md §9.11,
"singolo decoder condiviso" — chiarito dall'utente: una playlist
UNICA, trasmessa uguale su ogni server dove è attiva, non una
riproduzione indipendente per server).

L'idea centrale: la radio ha un "orologio" che avanza in base al
tempo reale trascorso, indipendentemente da quanti server sono
collegati in un dato momento — esattamente come una vera stazione
radio continua a trasmettere anche se nessuno la sta ascoltando in
quel momento. Quando un server si aggancia (o si riaggancia dopo che
il bot era stato spento), calcola PRIMA dove dovrebbe essere la
riproduzione ORA (che traccia, e a che punto), poi joina esattamente
lì — "riprenderà esattamente nel punto dove è stato lasciato", come
richiesto esplicitamente, non dall'inizio e non da una traccia
diversa.

Nessuna rete o Discord qui dentro — solo aritmetica su durate e
timestamp, interamente testabile senza nulla di esterno.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class RadioTrackInfo:
    """Una voce della playlist, con la sua durata — servono le
    durate di OGNI traccia per calcolare quanto tempo reale è
    passato attraversando la playlist dalla traccia di partenza."""

    identifier: str  # query/URL o "local:/percorso/assoluto"
    duration_ms: int


@dataclass(frozen=True)
class RadioPosition:
    track_index: int
    elapsed_ms_in_track: int


def compute_current_position(
    tracks: list[RadioTrackInfo],
    track_index_at_reference: int,
    reference_started_at: datetime,
    now: datetime,
) -> RadioPosition | None:
    """
    Dove dovrebbe essere la riproduzione ADESSO, partendo dal fatto
    noto che la traccia all'indice track_index_at_reference è
    iniziata a reference_started_at. Attraversa in avanti le tracce
    successive (con loop sulla playlist quando arriva alla fine —
    la radio non si ferma mai da sola) finché il tempo trascorso da
    reference_started_at a now non è "consumato" dalla durata delle
    tracce percorse.

    None se la playlist è vuota (nessuna radio possibile) o se
    track_index_at_reference è fuori range (stato incoerente,
    il chiamante decide come reagire — qui non si indovina).
    """
    if not tracks:
        return None
    if not (0 <= track_index_at_reference < len(tracks)):
        return None

    millisecondi_trascorsi = int((now - reference_started_at).total_seconds() * 1000)
    if millisecondi_trascorsi < 0:
        # L'orologio di riferimento è nel futuro (errore altrove, o
        # now passato per sbaglio) - restiamo alla traccia di
        # riferimento stessa, a inizio traccia, piuttosto che
        # produrre un indice o una posizione senza senso.
        return RadioPosition(track_index=track_index_at_reference, elapsed_ms_in_track=0)

    indice = track_index_at_reference
    rimanente = millisecondi_trascorsi

    # Limite di sicurezza: con una playlist di sole tracce a durata
    # zero (dato malformato) questo ciclo non deve girare all'infinito.
    massimo_giri = len(tracks) * 100_000 + 1
    giri = 0

    while True:
        durata = max(1, tracks[indice].duration_ms)  # evita divisione/loop infiniti su durata 0
        if rimanente < durata:
            return RadioPosition(track_index=indice, elapsed_ms_in_track=rimanente)
        rimanente -= durata
        indice = (indice + 1) % len(tracks)
        giri += 1
        if giri > massimo_giri:
            return RadioPosition(track_index=indice, elapsed_ms_in_track=0)


def next_track_index(current_index: int, total_tracks: int) -> int:
    """Il prossimo indice, con loop automatico sulla playlist — la
    radio non si ferma mai da sola quando arriva alla fine."""
    if total_tracks <= 0:
        return 0
    return (current_index + 1) % total_tracks
