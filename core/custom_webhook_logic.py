"""
core/custom_webhook_logic.py
================================
Logica pura del webhook custom in RICEZIONE (SPEC.md §10.8, la
parte "webhook" — la parte RSS esiste già in core/feed_watcher.py).
Nessuna dipendenza da aiohttp/discord.py qui dentro: generazione del
token, costruzione dell'URL da condividere con terzi, ed estrazione/
formattazione del messaggio dal payload JSON ricevuto.

A differenza di RSS/Twitch (dove il bot fa polling PERIODICO verso
un servizio esterno), qui è il contrario: un servizio terzo (un
webhook di GitHub, un monitor di uptime, IFTTT, uno script
qualunque...) fa una richiesta PUSH verso un endpoint HTTPS che
QUESTO bot deve esporre — core/custom_webhook_server.py. Stesso
principio già usato per la callback OAuth2 del restore (SPEC.md
§11.11, core/restore_web_server.py): un piccolo server aiohttp
dedicato, un URL segreto per webhook (il "token") al posto di una
sessione, così chiunque conosca l'URL può pubblicare in QUEL canale
e in nessun altro.
"""

from __future__ import annotations

import secrets

DEFAULT_MESSAGE_TEMPLATE = "📩 **{label}**\n{title}\n{message}\n{url}"

# Limiti di lunghezza per i campi presi dal payload di terzi — un
# messaggio Discord ha un tetto di 2000 caratteri, e un mittente
# esterno (non controllato da noi) potrebbe mandare qualunque cosa,
# per errore o apposta. Troncare qui, non lasciare che sia Discord a
# rifiutare l'intero invio con un errore poco chiaro.
MAX_TITLE_LENGTH = 256
MAX_MESSAGE_LENGTH = 1500
MAX_URL_LENGTH = 500


def generate_webhook_token() -> str:
    """
    Token segreto che identifica l'endpoint — l'unica cosa che
    autentica una richiesta in arrivo (nessun account/OAuth per un
    servizio terzo generico: è la stessa logica di un webhook
    incoming di Discord/Slack/GitHub, un URL-segreto). 32 byte da
    `secrets.token_urlsafe` — casualmente sicuro, non un ID
    incrementale indovinabile.
    """
    return secrets.token_urlsafe(32)


def build_webhook_url(base_url: str, token: str) -> str:
    """
    Unisce l'URL pubblico base (configurato dall'admin dell'istanza,
    dietro il proprio dominio/reverse proxy — ALERTS_WEBHOOK_PUBLIC_
    BASE_URL) con il percorso fisso `/webhook/<token>`. `base_url`
    con o senza "/" finale funziona lo stesso.
    """
    return f"{base_url.rstrip('/')}/webhook/{token}"


def _pulisci_campo(valore, lunghezza_massima: int) -> str:
    """
    Un payload di terzi è JSON arbitrario: il campo potrebbe mancare,
    essere `None`, o non essere una stringa (un numero, un booleano,
    una lista...) — normalizza tutto a stringa, mai un'eccezione per
    un tipo inatteso, e troncato al limite dato.
    """
    if valore is None:
        return ""
    testo = str(valore).strip()
    return testo[:lunghezza_massima]


def extract_webhook_fields(payload: dict) -> tuple[str, str, str]:
    """
    Estrae (title, message, url) da un payload JSON arbitrario
    inviato da un servizio terzo — nessuno schema fisso imposto:
    accetta alias comuni (`message`/`content`/`text` per il corpo,
    `url`/`link` per il link), il primo trovato tra gli alias vince.
    """
    if not isinstance(payload, dict):
        return "", "", ""

    title = _pulisci_campo(payload.get("title"), MAX_TITLE_LENGTH)

    corpo = payload.get("message")
    if corpo is None:
        corpo = payload.get("content")
    if corpo is None:
        corpo = payload.get("text")
    message = _pulisci_campo(corpo, MAX_MESSAGE_LENGTH)

    link = payload.get("url")
    if link is None:
        link = payload.get("link")
    url = _pulisci_campo(link, MAX_URL_LENGTH)

    return title, message, url


def render_webhook_message(template: str, label: str, payload: dict) -> str:
    """
    Applica il template (placeholder {label} {title} {message} {url},
    stesso stile dei template RSS già esistenti) e rimuove le righe
    rimaste vuote (title/message/url assenti dal payload) — un
    webhook che manda solo `{"message": "..."}` non deve produrre un
    messaggio Discord con due righe vuote in mezzo.
    """
    title, message, url = extract_webhook_fields(payload)
    testo = template.format(label=label, title=title, message=message, url=url)

    righe_non_vuote = [riga for riga in testo.split("\n") if riga.strip()]
    return "\n".join(righe_non_vuote)
