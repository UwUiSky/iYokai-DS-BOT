"""
core/web_panel_attivita.py
==========================
Activity «radio iYokai» (Embedded App SDK): la pagina che Discord apre dentro il client e lo stato della
radio condivisa in JSON. Le regole sono pure (provabili senza rete); `registra_rotte` le collega al pannello.
Funzioni coperte: SPEC B.8 (C17, C18; issue #107)
Dipende da: core/main_radio_logic.py, core/repositories/main_radio_repo.py
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from aiohttp import web

from core import main_radio_logic as radio
from core.repositories.main_radio_repo import main_radio_repo

MAX_TITOLO = 120
FLUSSO_VALIDO = re.compile(r"https://[^\s\"'<>]{1,300}")

ORIGINI_DISCORD = "https://discord.com https://ptb.discord.com https://canary.discord.com"


def intestazioni_attivita(https: bool) -> dict[str, str]:
    """Intestazioni della pagina dentro Discord: può stare in un riquadro solo dentro Discord."""
    csp = (
        "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' https://cdn.discordapp.com; "
        "connect-src 'self' https://discord.com; media-src https:; "
        f"frame-ancestors {ORIGINI_DISCORD}; base-uri 'none'"
    )
    intestazioni = {
        "Content-Security-Policy": csp,
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "same-origin",
        "Cache-Control": "no-store",
    }
    if https:
        intestazioni["Strict-Transport-Security"] = "max-age=31536000"
    return intestazioni


def e_apertura_attivita(percorso: str, query) -> bool:
    """Discord apre l'Activity su `/?frame_id=…&instance_id=…`; la pagina radio vive anche su `/attivita/…`."""
    if percorso.startswith("/attivita/"):
        return True
    return percorso == "/" and "frame_id" in query and "instance_id" in query


def flusso_valido(url: str) -> str:
    """Solo indirizzi https (la pagina sta dentro Discord): altro vale «nessun flusso»."""
    url = (url or "").strip()
    return url if FLUSSO_VALIDO.fullmatch(url) else ""


def stato_radio(tracce, stato, adesso: datetime) -> dict:
    """
    Cosa mostrare: il brano in onda e a che punto è. Spenta o vuota: `attiva` falso e nient'altro.
    Mai gli identificatori interni delle tracce (possono essere percorsi del server).
    """
    if stato is None or not stato.is_active or not tracce:
        return {"attiva": False}
    informazioni = [radio.RadioTrackInfo(identifier=t.identifier, duration_ms=t.duration_ms) for t in tracce]
    posizione = radio.compute_current_position(informazioni, stato.track_index, stato.track_started_at, adesso)
    if posizione is None:
        return {"attiva": False}
    brano = tracce[posizione.track_index]
    return {
        "attiva": True,
        "titolo": (brano.label or "?")[:MAX_TITOLO],
        "durata_ms": max(1, brano.duration_ms),
        "trascorso_ms": posizione.elapsed_ms_in_track,
        "numero": posizione.track_index + 1,
        "totale": len(tracce),
    }


def registra_rotte(app: web.Application, *, ambiente, client_id: str, flusso: str, testo_spenta: str):
    """Le due rotte pubbliche. `ambiente`: Jinja2 del pannello. Ritorna la funzione che disegna la pagina."""

    def pagina() -> web.Response:
        testo = ambiente.get_template("radio.html").render(
            client_id=client_id, flusso=flusso_valido(flusso), testo_spenta=testo_spenta
        )
        return web.Response(text=testo, content_type="text/html")

    async def pagina_radio(request: web.Request) -> web.Response:
        return pagina()

    async def stato_json(request: web.Request) -> web.Response:
        tracce = await main_radio_repo.list_tracks()
        stato = await main_radio_repo.get_state()
        return web.json_response(stato_radio(tracce, stato, datetime.now(timezone.utc)))

    app.router.add_get("/attivita/radio", pagina_radio)
    app.router.add_get("/attivita/radio/stato", stato_json)
    return pagina
