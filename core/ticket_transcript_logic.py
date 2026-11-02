"""
core/ticket_transcript_logic.py
===============================
Transcript HTML e ZIP degli allegati dei ticket (TKT-070, 071, 074). Funzioni pure, senza Discord.
Il file HTML non apre mai risorse remote (CSP + niente avatar o immagini dal CDN) e ogni testo passa
dall'autoescape di jinja2. Le immagini entrano solo come copia ricodificata dalla pipeline (D62), mai l'originale.
Funzioni coperte: SPEC §13.22
"""

from __future__ import annotations

import base64
import io
import re
import zipfile
from dataclasses import dataclass, field

from jinja2 import Environment

FORMATI = ("testo", "html", "entrambi")
MAX_BYTE_FILE = 8 * 1024 * 1024  # sotto i 10 MiB di Discord (LIM-55) con margine
MAX_IMMAGINI = 25  # per transcript: oltre, solo nome e impronta
MAX_BYTE_IMMAGINI_ZIP = 7 * 1024 * 1024
CSP = "default-src 'none'; style-src 'unsafe-inline'; img-src data:"
_SPAZI = re.compile(r"\s+")


def formato_valido(formato: str | None) -> str:
    return formato if formato in FORMATI else "testo"


@dataclass(frozen=True)
class AllegatoT:
    nome: str
    peso: int = 0
    sha256: str = ""
    png: bytes = b""  # copia ricodificata dalla pipeline; vuota = niente anteprima


@dataclass(frozen=True)
class MessaggioT:
    ora: str
    autore: str
    testo: str = ""
    allegati: tuple[AllegatoT, ...] = ()
    bot: bool = False


@dataclass(frozen=True)
class IntestazioneT:
    numero: int
    righe: tuple[tuple[str, str], ...] = field(default=())
    avviso: str | None = None


def iniziali(nome: str) -> str:
    """Due lettere al posto dell'avatar: nessuna immagine remota."""
    parole = [p for p in _SPAZI.split(nome.strip()) if p]
    if not parole:
        return "?"
    lettere = parole[0][0] + (parole[1][0] if len(parole) > 1 else (parole[0][1] if len(parole[0]) > 1 else ""))
    return lettere.upper()


def _data_uri(png: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")


_ambiente = Environment(autoescape=True)
_ambiente.filters["iniziali"] = iniziali
_ambiente.filters["uri"] = _data_uri

_MESSAGGIO = _ambiente.from_string(
    """<div class="m{% if m.bot %} b{% endif %}"><div class="a">{{ m.autore|iniziali }}</div><div class="c">
<div class="h"><b>{{ m.autore }}</b> <span>{{ m.ora }}</span></div>
<div class="t">{{ m.testo if m.testo else "(nessun testo)" }}</div>
{% for a in m.allegati %}<div class="f">{% if a.png and immagini %}<img alt="{{ a.nome }}" src="{{ a.png|uri }}">{% endif %}
<small>{{ a.nome }}{% if a.peso %} · {{ a.peso }} byte{% endif %}{% if a.sha256 %} · SHA-256 {{ a.sha256 }}{% endif %}</small></div>{% endfor %}
</div></div>"""
)

_PAGINA = _ambiente.from_string(
    """<!doctype html>
<html lang="it"><head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="{{ csp }}">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Transcript ticket #{{ '%04d'|format(h.numero) }}{% if parte %} (parte {{ parte[0] }} di {{ parte[1] }}){% endif %}</title>
<style>
:root{--bg:#fff;--fg:#1f2328;--sub:#59636e;--card:#f3f4f6}
@media (prefers-color-scheme:dark){:root{--bg:#1e1f22;--fg:#dbdee1;--sub:#949ba4;--card:#2b2d31}}
body{background:var(--bg);color:var(--fg);font:15px/1.4 system-ui,sans-serif;margin:0;padding:16px;max-width:860px}
.m{display:flex;gap:12px;padding:8px 0}.a{flex:none;width:40px;height:40px;border-radius:50%;background:var(--card);
display:flex;align-items:center;justify-content:center;font-weight:700}.b .a{background:#5865f2;color:#fff}
.h span,.f small{color:var(--sub);font-size:12px}.t{white-space:pre-wrap;overflow-wrap:anywhere}
.f img{display:block;max-width:100%;max-height:360px;border-radius:6px;margin-top:6px}
.i{background:var(--card);border-radius:8px;padding:12px;margin-bottom:12px}.w{border-left:4px solid #f0b232;padding-left:8px}
</style></head><body>
<div class="i"><h1>Ticket #{{ '%04d'|format(h.numero) }}{% if parte %} · parte {{ parte[0] }} di {{ parte[1] }}{% endif %}</h1>
{% for k, v in h.righe %}<div><b>{{ k }}:</b> {{ v }}</div>{% endfor %}
{% if h.avviso %}<p class="w">{{ h.avviso }}</p>{% endif %}</div>
{{ corpo|safe }}
</body></html>"""
)


def _corpo(messaggi, immagini: bool) -> str:
    if not messaggi:
        return '<div class="m"><div class="t">(nessun messaggio nel canale)</div></div>'
    return "\n".join(_MESSAGGIO.render(m=m, immagini=immagini) for m in messaggi)


def _pagina(h: IntestazioneT, corpo: str, parte: tuple[int, int] | None) -> str:
    return _PAGINA.render(h=h, corpo=corpo, csp=CSP, parte=parte)


def _pesa(testo: str) -> int:
    return len(testo.encode("utf-8"))


def html_in_parti(
    h: IntestazioneT, messaggi: list[MessaggioT], max_byte: int = MAX_BYTE_FILE
) -> list[str]:
    """
    Le pagine HTML del transcript. Prima con le immagini; se il file supera `max_byte` si
    tolgono le immagini; se ancora troppo grande si divide in parti (a fine messaggio).
    """
    con_immagini = _pagina(h, _corpo(messaggi, True), None)
    if _pesa(con_immagini) <= max_byte:
        return [con_immagini]
    senza = _pagina(h, _corpo(messaggi, False), None)
    if _pesa(senza) <= max_byte:
        return [senza]
    margine = _pesa(_pagina(h, "", (99, 99))) + 64
    gruppi: list[list[str]] = [[]]
    peso = margine
    for m in messaggi:
        pezzo = _MESSAGGIO.render(m=m, immagini=False)
        if len(pezzo.encode("utf-8")) > max_byte - margine:
            pezzo = _MESSAGGIO.render(
                m=MessaggioT(m.ora, m.autore, m.testo[: max(0, (max_byte - margine) // 8)] + " […]", (), m.bot), immagini=False
            )
        p = _pesa(pezzo) + 1
        if peso + p > max_byte and gruppi[-1]:
            gruppi.append([])
            peso = margine
        gruppi[-1].append(pezzo)
        peso += p
    totale = len(gruppi)
    return [_pagina(h, "\n".join(g), (i, totale)) for i, g in enumerate(gruppi, start=1)]


def nomi_immagini(allegati: list[AllegatoT]) -> list[tuple[str, AllegatoT]]:
    """Nome stabile dentro lo ZIP per ogni immagine ricodificata: numero + impronta, mai il nome dell'utente."""
    return [(f"immagine-{i:03d}-{(a.sha256 or 'x')[:8]}.png", a) for i, a in enumerate(allegati, start=1) if a.png]


def zip_allegati(allegati: list[AllegatoT]) -> bytes | None:
    """
    ZIP con le sole immagini ricodificate e un elenco di tutti gli allegati (nome, peso, impronta, se inclusa).
    Mai i file originali. None se non c'è niente da mettere.
    """
    if not allegati:
        return None
    incluse = nomi_immagini(allegati)
    righe = []
    peso = 0
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
        dentro: dict[int, str] = {}
        for nome_zip, a in incluse:
            if peso + len(a.png) > MAX_BYTE_IMMAGINI_ZIP:
                continue
            z.writestr(nome_zip, a.png)
            peso += len(a.png)
            dentro[id(a)] = nome_zip
        for a in allegati:
            stato = f"nel file {dentro[id(a)]}" if id(a) in dentro else "non incluso (solo immagini controllate)"
            righe.append(f"{a.nome}\t{a.peso} byte\tSHA-256 {a.sha256 or 'n/d'}\t{stato}")
        z.writestr("elenco-allegati.txt", "\n".join(righe) + "\n")
    return buffer.getvalue()
