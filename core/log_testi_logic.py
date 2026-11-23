"""
core/log_testi_logic.py
=======================
Testo dei messaggi dei canali registrati, conservato SOLO cifrato (LOG-029, D122): scelta della chiave, cifratura di una
riga e dell'archivio di un caso (AES-256-GCM di `core/oauth_crypto`, dato associato legato al server e al messaggio o al
caso), scheda degli allegati (nome, tipo e peso: mai i byte, D74) e pagina HTML dell'archivio, con ogni testo ripulito.
Funzioni pure, senza Discord né database. Senza chiave non si salva nulla.
Funzioni coperte: SPEC §8.18 (LOG-029)
Dipende da: core/oauth_crypto.py, core/allegati_tipo_logic.py
"""

from __future__ import annotations

import html
import json
from dataclasses import dataclass
from datetime import datetime, timezone

from cryptography.exceptions import InvalidTag

from core import oauth_crypto
from core.allegati_tipo_logic import nome_pulito

GIORNI_FINESTRA = 7  # i messaggi normali restano 7 giorni (scadenza dal registro dei dati)
GIORNI_ARCHIVIO = 3  # a ogni sanzione si copiano i messaggi degli ultimi 3 giorni
MAX_TESTO = 4000  # caratteri di un messaggio (Discord ne ammette 4000)
MAX_ALLEGATI = 10
MAX_RIGHE_SERVER = 20_000  # tetto per server nella tabella a finestra
MAX_MESSAGGI_ARCHIVIO = 1000
MAX_BYTE_ARCHIVIO = 2_000_000
EVENTI = ("creato", "modificato", "cancellato")
ETICHETTE = {"creato": "scritto", "modificato": "modificato", "cancellato": "cancellato"}

# Pagina dell'archivio: solo stile interno, niente script, niente risorse esterne.
INTESTAZIONI_PAGINA = {
    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'; "
                               "frame-ancestors 'none'; sandbox",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Cache-Control": "no-store",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Resource-Policy": "same-origin",
}


def chiave_da_config(cfg) -> str:
    """Chiave dedicata, poi quella delle trascrizioni dei ticket, poi quella dei token OAuth. Vuota = niente testo."""
    for nome in ("LOG_TESTI_KEY", "TICKET_TRASCRIZIONI_KEY", "OAUTH_ENCRYPTION_KEY"):
        valore = (getattr(cfg, nome, "") or "").strip()
        if valore:
            return valore
    return ""


def indirizzo_archivio(base_pubblica: str, guild_id: int, case_number: int) -> str:
    """Il link della pagina dell'archivio di un caso, o "" se l'indirizzo pubblico del pannello non è configurato."""
    base = (base_pubblica or "").strip().rstrip("/")
    return f"{base}/server/{int(guild_id)}/moderazione/archivio/{int(case_number)}" if base.startswith(("https://", "http://")) else ""


def scheda_allegati(allegati) -> list[dict]:
    """Solo nome pulito, tipo e peso (D74). `allegati`: oggetti con filename, content_type e size."""
    scheda = []
    for a in list(allegati or [])[:MAX_ALLEGATI]:
        scheda.append({
            "nome": nome_pulito(getattr(a, "filename", "")) or "senza nome",
            "tipo": str(getattr(a, "content_type", "") or "sconosciuto")[:80],
            "peso": max(0, int(getattr(a, "size", 0) or 0)),
        })
    return scheda


def _aad_riga(guild_id: int, message_id: int, user_id: int, evento: str) -> bytes:
    return f"log-testo:{guild_id}:{message_id}:{user_id}:{evento}".encode("ascii")


def cifra_riga(guild_id: int, message_id: int, user_id: int, evento: str, testo: str, allegati: list[dict], chiave: str) -> str:
    """Il testo di un evento, cifrato. Copiato su un'altra riga (altro server, messaggio o autore) non si apre più."""
    corpo = json.dumps({"v": 1, "testo": (testo or "")[:MAX_TESTO], "allegati": allegati[:MAX_ALLEGATI]}, ensure_ascii=False)
    return oauth_crypto.encrypt_token(corpo, chiave, aad=_aad_riga(guild_id, message_id, user_id, evento))


def apri_riga(cifrato: str, guild_id: int, message_id: int, user_id: int, evento: str, chiave: str) -> tuple[str, list[dict]] | None:
    """(testo, allegati), o None se alterato, di un'altra riga o senza la chiave giusta."""
    try:
        dati = json.loads(oauth_crypto.decrypt_token(cifrato, chiave, aad=_aad_riga(guild_id, message_id, user_id, evento)))
        testo, allegati = dati["testo"], dati.get("allegati") or []
    except (InvalidTag, oauth_crypto.OAuthEncryptionNotConfigured, ValueError, KeyError, TypeError):
        return None
    if not isinstance(testo, str) or not isinstance(allegati, list):
        return None
    return testo, [a for a in allegati if isinstance(a, dict)]


@dataclass(frozen=True)
class MessaggioArchivio:
    quando: datetime
    canale_id: int
    messaggio_id: int
    evento: str
    testo: str
    allegati: tuple = ()


def _aad_archivio(guild_id: int, case_number: int) -> bytes:
    return f"log-archivio:{guild_id}:{case_number}".encode("ascii")


def cifra_archivio(messaggi: list[MessaggioArchivio], guild_id: int, case_number: int, utente_id: int, chiave: str) -> str:
    """L'archivio del caso (i messaggi dell'utente degli ultimi 3 giorni), cifrato e legato a server e caso."""
    righe = []
    peso = 0
    for m in sorted(messaggi, key=lambda x: x.quando)[-MAX_MESSAGGI_ARCHIVIO:]:
        riga = {"q": m.quando.astimezone(timezone.utc).isoformat(), "c": m.canale_id, "m": m.messaggio_id,
                "e": m.evento, "t": m.testo, "a": list(m.allegati)}
        peso += len(json.dumps(riga, ensure_ascii=False))
        if peso > MAX_BYTE_ARCHIVIO:
            break
        righe.append(riga)
    corpo = json.dumps({"v": 1, "utente": utente_id, "messaggi": righe}, ensure_ascii=False)
    return oauth_crypto.encrypt_token(corpo, chiave, aad=_aad_archivio(guild_id, case_number))


def apri_archivio(cifrato: str, guild_id: int, case_number: int, chiave: str) -> tuple[int, list[MessaggioArchivio]] | None:
    """(utente, messaggi) oppure None se alterato, di un altro caso o la chiave non c'è più."""
    try:
        dati = json.loads(oauth_crypto.decrypt_token(cifrato, chiave, aad=_aad_archivio(guild_id, case_number)))
        utente = int(dati["utente"])
        messaggi = [
            MessaggioArchivio(
                datetime.fromisoformat(r["q"]), int(r["c"]), int(r["m"]), str(r["e"]), str(r["t"]),
                tuple(a for a in (r.get("a") or []) if isinstance(a, dict)),
            )
            for r in dati["messaggi"]
        ]
    except (InvalidTag, oauth_crypto.OAuthEncryptionNotConfigured, ValueError, KeyError, TypeError, AttributeError):
        return None
    return utente, messaggi


def _scheda_testo(a: dict) -> str:
    try:
        kib = max(0, int(a.get("peso", 0))) // 1024
    except (TypeError, ValueError):
        kib = 0
    return f"{a.get('nome', '?')} ({a.get('tipo', '?')}, {kib} KiB)"


def pagina_html(messaggi: list[MessaggioArchivio], case_number: int, utente_id: int) -> str:
    """La pagina dell'archivio. Ogni testo passa da `html.escape`: nessun contenuto di un utente è mai markup."""
    e = html.escape
    corpo = []
    for m in sorted(messaggi, key=lambda x: x.quando):
        quando = m.quando.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        allegati = "".join(f"<li>{e(_scheda_testo(a))}</li>" for a in m.allegati)
        corpo.append(
            f"<article><header><time>{e(quando)}</time> · canale {int(m.canale_id)} · "
            f"messaggio {int(m.messaggio_id)} · {e(ETICHETTE.get(m.evento, m.evento))}</header>"
            f"<p>{e(m.testo) or '<i>(senza testo)</i>'}</p>" + (f"<ul>{allegati}</ul>" if allegati else "") + "</article>"
        )
    vuota = "<p>Nessun messaggio salvato per questo utente negli ultimi 3 giorni.</p>" if not corpo else ""
    return (
        "<!doctype html><html lang=\"it\"><head><meta charset=\"utf-8\"><meta name=\"robots\" content=\"noindex\">"
        f"<title>Archivio del caso {int(case_number)}</title><style>"
        "body{background:#07070b;color:#c8c4bc;font:16px/1.65 system-ui,sans-serif;max-width:46rem;margin:2rem auto;padding:0 1rem}"
        "article{border-left:2px solid #2a2928;padding:.25rem 1rem;margin:1rem 0}header{color:#8a8680;font-size:.85rem}"
        "p{white-space:pre-wrap;overflow-wrap:anywhere;margin:.4rem 0}</style></head><body>"
        f"<h1>Archivio del caso {int(case_number)}</h1>"
        f"<p>Messaggi dell'utente {int(utente_id)} negli ultimi {GIORNI_ARCHIVIO} giorni prima della sanzione. "
        "Dei file allegati restano solo nome, tipo e peso.</p>" + vuota + "".join(corpo) + "</body></html>"
    )
