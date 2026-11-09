"""
core/tag_pacchetti_logic.py
===========================
Pacchetti di tag da condividere (codice valido 7 giorni, o file JSON fino a 1 MiB): scrittura, lettura con controllo di
ogni riga, sostituzione di un testo. Un pacchetto non porta ruoli né canali (sono di un solo server). Nessun accesso a Discord.
Funzioni coperte: catalogo #128 UTL-039, 040, 041 (D69, B21)
"""

from __future__ import annotations

import json
import secrets

from core.custom_command_logic import INVII, MAX_PAUSA, MAX_PESO, MAX_TAG, MAX_TESTO, PERMESSI_TAG, leggi_reazioni
from core.nome_logic import normalizza_nome

MAX_BYTE_PACCHETTO = 1024 * 1024
GIORNI_CODICE = 7
VERSIONE = 1
_CAMPI_SEMPLICI = ("use_embed", "bersaglio", "cancella_innesco", "solo_nsfw", "anche_modificati")


class PacchettoErrato(ValueError):
    """Il pacchetto non si può leggere: il testo è la chiave del messaggio per chi ha dato il comando."""


def nuovo_codice() -> str:
    return secrets.token_urlsafe(6).replace("_", "x").replace("-", "y")[:8]


def pacchetto_da_tag(tags: list, risposte: dict[str, list[tuple[int, str]]]) -> dict:
    """Il contenuto di un pacchetto (senza ruoli, canali, usi o autori)."""
    voci = []
    for t in tags[:MAX_TAG]:
        voci.append({
            "nome": t.name, "testo": t.response, "pausa": t.cooldown_seconds, "permesso": t.permesso, "invio": "canale" if t.invio == "altro" else t.invio,
            "reazioni": list(t.reazioni or ()), "si_cancella_dopo": t.si_cancella_dopo, "cancella_messaggi": t.cancella_messaggi,
            "gruppo": t.gruppo, "risposte": [[p, x] for p, x in risposte.get(t.name, [])],
            **{c: bool(getattr(t, c)) for c in _CAMPI_SEMPLICI},
        })
    return {"versione": VERSIONE, "tag": voci}


def pacchetto_in_file(dati: dict) -> bytes:
    return json.dumps(dati, ensure_ascii=False, indent=1).encode("utf-8")


def leggi_pacchetto(grezzo: bytes | str | dict) -> list[dict]:
    """Le righe valide del pacchetto, già pulite. Salta quelle sbagliate; solleva PacchettoErrato se non c'è nulla da leggere."""
    if isinstance(grezzo, (bytes, str)):
        if len(grezzo) > MAX_BYTE_PACCHETTO:
            raise PacchettoErrato("tag_pacchetto_grande")
        try:
            grezzo = json.loads(grezzo)
        except (ValueError, UnicodeDecodeError):
            raise PacchettoErrato("tag_pacchetto_illeggibile") from None
    voci = grezzo.get("tag") if isinstance(grezzo, dict) else None
    if not isinstance(voci, list):
        raise PacchettoErrato("tag_pacchetto_illeggibile")
    pulite, visti = [], set()
    for v in voci[:MAX_TAG]:
        if not isinstance(v, dict):
            continue
        nome = normalizza_nome(v["nome"]) if isinstance(v.get("nome"), str) else None
        testo = v.get("testo")
        if nome is None or nome in visti or not isinstance(testo, str) or not 1 <= len(testo) <= MAX_TESTO:
            continue
        visti.add(nome)
        reazioni = leggi_reazioni(" ".join(v["reazioni"])) if isinstance(v.get("reazioni"), list) and all(isinstance(x, str) for x in v["reazioni"]) else []
        risposte = []
        for coppia in (v.get("risposte") if isinstance(v.get("risposte"), list) else [])[:5]:
            if (isinstance(coppia, list) and len(coppia) == 2 and isinstance(coppia[0], int) and 1 <= coppia[0] <= MAX_PESO
                    and isinstance(coppia[1], str) and 1 <= len(coppia[1]) <= MAX_TESTO):
                risposte.append((coppia[0], coppia[1]))
        intero = lambda k, a, b: v[k] if isinstance(v.get(k), int) and not isinstance(v.get(k), bool) and a <= v[k] <= b else None  # noqa: E731
        pulite.append({
            "nome": nome, "testo": testo, "pausa": intero("pausa", 0, MAX_PAUSA) or 0,
            "permesso": v["permesso"] if v.get("permesso") in PERMESSI_TAG else None,
            "invio": v["invio"] if v.get("invio") in INVII and v["invio"] != "altro" else "canale",
            "reazioni": reazioni or [], "si_cancella_dopo": intero("si_cancella_dopo", 5, 3600), "cancella_messaggi": intero("cancella_messaggi", 1, 100),
            "gruppo": v["gruppo"][:32] if isinstance(v.get("gruppo"), str) and v["gruppo"].strip() else None, "risposte": risposte,
            **{c: v.get(c) is True for c in _CAMPI_SEMPLICI},
        })
    if not pulite:
        raise PacchettoErrato("tag_pacchetto_vuoto")
    return pulite


def nome_gruppo_valido(nome: str) -> str | None:
    pulito = nome.strip().lower()
    return pulito if 1 <= len(pulito) <= 32 and all(c.isalnum() or c in "-_" for c in pulito) else None
