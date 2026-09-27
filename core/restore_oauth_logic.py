"""
core/restore_oauth_logic.py
===============================
Logica pura del restore utenti via OAuth2 (SPEC.md §11.11) — costruzione
dell'URL di autorizzazione e dello "state" che lo accompagna, senza
alcuna chiamata di rete: quella vive in core/restore_orchestrator.py.

Lo "state" OAuth2 è il meccanismo standard per far tornare al
callback il CONTESTO della richiesta (per chi era, verso quale
server) — Discord lo restituisce invariato insieme al `code`. Qui è
semplicemente `"{source_guild_id}:{target_guild_id}:{user_id}"`: non
contiene segreti (l'utente che clicca il link lo vede comunque), il
suo unico scopo è farci sapere COSA fare quando arriva la callback,
non autenticare nessuno (l'autenticazione vera è nel `code` scambiato
lato server con Discord).
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlencode

DISCORD_AUTHORIZE_URL = "https://discord.com/oauth2/authorize"
OAUTH_SCOPES = "identify guilds.join"


@dataclass(frozen=True)
class RestoreState:
    source_guild_id: int
    target_guild_id: int
    user_id: int


def encode_state(state: RestoreState) -> str:
    return f"{state.source_guild_id}:{state.target_guild_id}:{state.user_id}"


def decode_state(raw: str) -> RestoreState | None:
    """None se la stringa non ha la forma attesa — un callback con
    uno state manomesso/scaduto/di un altro flusso OAuth non deve far
    sollevare un'eccezione, va semplicemente ignorato come non
    valido."""
    pezzi = raw.split(":")
    if len(pezzi) != 3:
        return None
    try:
        return RestoreState(
            source_guild_id=int(pezzi[0]),
            target_guild_id=int(pezzi[1]),
            user_id=int(pezzi[2]),
        )
    except ValueError:
        return None


def build_authorize_url(
    client_id: str, redirect_uri: str, source_guild_id: int, target_guild_id: int, user_id: int
) -> str:
    """
    URL da mandare in DM all'utente da ripristinare — cliccandolo,
    autorizza iYokai a: leggere la sua identità (`identify`) e
    aggiungerlo a un server (`guilds.join`, richiede che iYokai Main
    abbia i permessi di gestione membri nel server di destinazione).
    """
    state = encode_state(
        RestoreState(source_guild_id=source_guild_id, target_guild_id=target_guild_id, user_id=user_id)
    )
    query = urlencode(
        {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": OAUTH_SCOPES,
            "state": state,
        }
    )
    return f"{DISCORD_AUTHORIZE_URL}?{query}"
