"""
core/moderation_esporta_chat.py
===============================
Il file di testo con gli ultimi messaggi di un canale (`/mod-canali esporta-chat`). Senza Discord: si prova con messaggi finti.
Funzioni coperte: UTL-204 (D74: degli allegati restano solo nome pulito, tipo e peso, mai l'originale né il suo indirizzo)
"""

from __future__ import annotations

import re
import unicodedata

MAX_MESSAGGI = 1000
MAX_BYTE = 9_500_000  # D74: file inviati sotto 9,5 MiB (il tetto del bot è più basso di quello di Discord)
MAX_NOME_ALLEGATO = 80

_CONTROLLO = re.compile(r"[\x00-\x08\x0b-\x1f\x7f​-‏‪-‮⁦-⁩]")


def nome_pulito(nome: str) -> str:
    """Solo il nome del file, senza percorsi né caratteri di controllo."""
    nome = unicodedata.normalize("NFKC", nome or "file").replace("\\", "/").rsplit("/", 1)[-1]
    nome = _CONTROLLO.sub("", nome).strip()
    return (nome or "file")[:MAX_NOME_ALLEGATO]


def _scheda_allegato(a) -> str:
    tipo = (getattr(a, "content_type", None) or "tipo sconosciuto").split(";")[0][:60]
    return f"[allegato: {nome_pulito(a.filename)}, {_CONTROLLO.sub('', tipo)}, {max(0, int(a.size or 0)) // 1024} KB]"


def riga_messaggio(m) -> str:
    """Una riga per messaggio (le righe a capo del testo restano, rientrate)."""
    autore = f"{_CONTROLLO.sub('', m.author.display_name)} ({m.author.id})"
    testo = _CONTROLLO.sub("", m.content or "").replace("\n", "\n    ")
    pezzi = [testo] if testo else []
    pezzi += [_scheda_allegato(a) for a in m.attachments]
    if getattr(m, "embeds", None):
        pezzi.append(f"[{len(m.embeds)} embed]")
    if getattr(m, "stickers", None):
        pezzi.append(f"[{len(m.stickers)} sticker]")
    return f"[{m.created_at:%Y-%m-%d %H:%M:%S}] {autore}: {' '.join(pezzi) or '[vuoto]'}"


def costruisci_file(messaggi, nome_canale: str) -> tuple[bytes, int, bool]:
    """(contenuto, messaggi scritti, tagliato). `messaggi` dal più vecchio al più nuovo; oltre i 9,5 MB si ferma."""
    intestazione = f"# Ultimi messaggi di #{_CONTROLLO.sub('', nome_canale)[:100]}\n"
    corpo = [intestazione]
    usati = len(intestazione.encode())
    scritti = 0
    for m in messaggi[:MAX_MESSAGGI]:
        riga = riga_messaggio(m) + "\n"
        pesa = len(riga.encode())
        if usati + pesa > MAX_BYTE:
            return "".join(corpo).encode(), scritti, True
        corpo.append(riga)
        usati += pesa
        scritti += 1
    return "".join(corpo).encode(), scritti, False
