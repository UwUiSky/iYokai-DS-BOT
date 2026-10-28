"""
core/voice_text_logic.py
========================
Il testo prima della sintesi: via markdown, emoji, indirizzi e menzioni; pause dalla punteggiatura; lunghezza
limitata; nomi di persona solo se si possono pronunciare. Logica pura, senza Discord.
Funzioni coperte: SPEC §14.19, §25.102, §25.105 (AI-R-109, AI-R-112)
"""

from __future__ import annotations

import re

MAX_CARATTERI = 400
MAX_FRASI = 6

_CODICE = re.compile(r"```.*?```|`[^`]*`", re.S)
_URL = re.compile(r"https?://\S+|www\.\S+", re.I)
_MENZIONE_UTENTE = re.compile(r"<@!?(\d+)>")
_MENZIONE_CANALE = re.compile(r"<#\d+>")
_MENZIONE_RUOLO = re.compile(r"<@&\d+>")
_EMOJI_SERVER = re.compile(r"<a?:\w+:\d+>")
_EMOJI = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF\U00002300-\U000023FF\U00002B00-\U00002BFF️‍⃣]"
)
_MARKDOWN = re.compile(r"(\*\*|__|~~|\|\||\*|_|^>+\s?|^#+\s?)", re.M)
_FINE = ".!?…"


def prepara(testo: str, nomi: dict[int, str] | None = None) -> str:
    """Testo naturale pronto per la voce; vuoto se non resta niente da dire."""
    t = _CODICE.sub(" ", testo or "")
    t = _EMOJI_SERVER.sub(" ", t)
    t = _URL.sub(" un link ", t)
    t = _MENZIONE_RUOLO.sub(" ", t)
    t = _MENZIONE_CANALE.sub(" un canale ", t)
    t = _MENZIONE_UTENTE.sub(lambda m: f" {nome_pronunciabile((nomi or {}).get(int(m.group(1)))) or ''} ", t)
    t = _EMOJI.sub(" ", t)
    t = _MARKDOWN.sub("", t)
    t = re.sub(r"[ \t]*\n+[ \t]*", ". ", t)
    t = re.sub(r"\s+", " ", t).strip(" ,;:-")
    t = re.sub(r"([.!?…])\s*\.", r"\1", t)
    if not t:
        return ""
    t = taglia_alla_frase(t, MAX_CARATTERI)
    return t if t[-1] in _FINE else t + "."


def taglia_alla_frase(testo: str, massimo: int) -> str:
    if len(testo) <= massimo:
        return testo
    taglio = max((testo.rfind(c, 0, massimo) for c in _FINE), default=-1)
    return testo[: taglio + 1] if taglio > massimo // 3 else testo[:massimo].rstrip() + "…"


def frasi(testo: str) -> list[str]:
    """Le frasi da leggere una per volta, con la pausa del profilo in mezzo."""
    pezzi = [p.strip() for p in re.split(r"(?<=[.!?…])\s+", testo) if p.strip()]
    return pezzi[:MAX_FRASI]


def nome_pronunciabile(nome: str | None) -> str | None:
    """Il nome se è fatto di lettere (2-20), ha vocali e non è una sigla o un codice; altrimenti None."""
    if not nome:
        return None
    if "_" in nome:
        return None  # nomi da gioco o da codice: meglio non pronunciarli
    pulito = re.sub(r"[^\w' -]", "", nome, flags=re.U).strip()
    pulito = re.sub(r"\d+", "", pulito).strip(" -_")
    if not 2 <= len(pulito) <= 20 or not re.search(r"[aeiouàèéìòùAEIOU]", pulito):
        return None
    if pulito.isupper() and len(pulito) > 3:
        return None
    if re.search(r"[bcdfghlmnpqrstvz]{5,}", pulito.lower()):
        return None
    return pulito.split()[0] if " " in pulito else pulito
