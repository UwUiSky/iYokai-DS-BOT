"""
core/twitch_api_logic.py
============================
Logica pura di Twitch live/offline (SPEC.md §10.1, §10.2). Nessuna
rete qui dentro — solo interpretazione delle risposte JSON
dell'API Helix di Twitch, già scaricate dal chiamante (core/
twitch_watcher.py).

Decisione tecnica: polling periodico sull'endpoint "Get Streams",
non EventSub webhook — stesso motivo già documentato per YouTube/
Reddit (nessun server web in questo bot).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TwitchStreamStatus:
    login: str
    is_live: bool
    title: str | None = None
    game_name: str | None = None


def parse_get_streams_response(payload: dict, logins_richiesti: list[str]) -> list[TwitchStreamStatus]:
    """
    L'API "Get Streams" di Twitch restituisce SOLO gli stream
    attualmente LIVE — chi non è live semplicemente non compare
    nella risposta, non viene segnalato esplicitamente come offline.
    Per questo il chiamante deve passare la lista completa dei login
    richiesti: ogni login assente dalla risposta viene qui
    esplicitamente marcato is_live=False, così il resto del sistema
    ha uno stato completo (live/offline) per ognuno, non solo per
    chi è in onda in questo momento.
    """
    dati = payload.get("data", [])
    login_live = {}
    for voce in dati:
        login = voce.get("user_login", "").lower()
        if not login:
            continue
        login_live[login] = TwitchStreamStatus(
            login=login,
            is_live=True,
            title=voce.get("title"),
            game_name=voce.get("game_name"),
        )

    risultati = []
    for login_richiesto in logins_richiesti:
        chiave = login_richiesto.lower()
        if chiave in login_live:
            risultati.append(login_live[chiave])
        else:
            risultati.append(TwitchStreamStatus(login=chiave, is_live=False))
    return risultati


def parse_app_access_token_response(payload: dict) -> tuple[str, int] | None:
    """
    (token, secondi_di_validità) dalla risposta OAuth Client
    Credentials di Twitch, o None se la risposta non ha la forma
    attesa (credenziali sbagliate, errore del servizio, ecc.) — il
    chiamante decide cosa fare in quel caso, qui solo interpretazione.
    """
    token = payload.get("access_token")
    scadenza = payload.get("expires_in")
    if not token or not isinstance(scadenza, int):
        return None
    return token, scadenza
