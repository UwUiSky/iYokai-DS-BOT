"""
core/kick_api_logic.py
======================
Legge le risposte dell'API pubblica di Kick (NF-32, SPEC §10.5). Nessuna rete:
solo interpretazione dei JSON già scaricati da core/kick_watcher.py.
L'API ufficiale (docs.kick.com) chiede un'app registrata (client id e secret
gratuiti) e un token "client credentials": senza le due variabili il watcher
resta inattivo, come per Twitch e YouTube.
Funzioni coperte: SPEC §10.13 (NF-32)
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Kick ammette lettere, cifre, trattini e underscore nello "slug" del canale.
_SLUG = re.compile(r"^[a-z0-9_-]{1,50}$")
MAX_SLUG_PER_RICHIESTA = 50


@dataclass(frozen=True)
class KickChannelStatus:
    slug: str
    is_live: bool
    title: str | None = None
    category: str | None = None


def normalizza_slug(testo: str) -> str | None:
    """Accetta lo slug o l'indirizzo kick.com/<slug>; None se non è valido."""
    t = (testo or "").strip().lower().rstrip("/")
    t = re.sub(r"^(https?://)?(www\.)?kick\.com/", "", t)
    return t if _SLUG.match(t) else None


def parse_token_response(payload) -> tuple[str, int] | None:
    if not isinstance(payload, dict):
        return None
    token, scade = payload.get("access_token"), payload.get("expires_in")
    if not isinstance(token, str) or not token or not isinstance(scade, (int, float)):
        return None
    return token, int(scade)


def parse_channels_response(payload, slug_richiesti: list[str]) -> list[KickChannelStatus]:
    """Uno stato per ogni slug richiesto; uno slug assente dalla risposta conta come non in diretta."""
    trovati: dict[str, KickChannelStatus] = {}
    dati = payload.get("data", []) if isinstance(payload, dict) else []
    for voce in dati if isinstance(dati, list) else []:
        if not isinstance(voce, dict) or not isinstance(voce.get("slug"), str):
            continue
        stream = voce.get("stream") if isinstance(voce.get("stream"), dict) else {}
        categoria = voce.get("category") if isinstance(voce.get("category"), dict) else {}
        slug = voce["slug"].lower()
        trovati[slug] = KickChannelStatus(
            slug=slug,
            is_live=bool(stream.get("is_live")),
            title=voce.get("stream_title") if isinstance(voce.get("stream_title"), str) else None,
            category=categoria.get("name") if isinstance(categoria.get("name"), str) else None,
        )
    return [trovati.get(s.lower(), KickChannelStatus(slug=s.lower(), is_live=False)) for s in slug_richiesti]
