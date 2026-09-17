"""
core/spam_trap_transcript.py
===============================
Generazione del transcript HTML dei messaggi di un utente bannato
dallo Spam Trap. Riceve dati già semplici (non oggetti discord.py),
quindi è testabile con valori finti qualsiasi, senza connessione a
Discord — il cog (cogs/security/spam_trap.py) fa da ponte, fetchando
i messaggi veri via REST e convertendoli in TranscriptEntry prima di
chiamare build_transcript_html().

Scope deliberatamente ridotto rispetto alla specifica originale: le
immagini degli allegati sono elencate per nome/dimensione/tipo, NON
rigenerate come thumbnail incorporate (che richiederebbe una libreria
di elaborazione immagini — Pillow — e una decisione su come
distribuire quella dipendenza, non ancora presa). Segnato così in
SPEC.md, non spacciato per completo.

Escaping: OGNI stringa che finisce nell'HTML passa da html.escape()
prima di essere inserita — un nickname o un contenuto messaggio con
"<script>" dentro non deve poter eseguire codice quando lo staff
apre il transcript nel browser.
"""

from __future__ import annotations

import html
from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class TranscriptEntry:
    timestamp: datetime
    author_display_name: str
    author_tag: str  # es. "utente#1234" o lo username univoco
    content: str  # testo grezzo, NON pre-escapato — lo fa build_transcript_html
    attachment_filenames: list[str] = field(default_factory=list)
    is_deleted_source: bool = False  # True se il messaggio non era più fetchabile (già cancellato)


def _escape(text: str) -> str:
    return html.escape(text, quote=True)


def build_transcript_html(
    entries: list[TranscriptEntry],
    title: str,
    generated_at: datetime,
) -> str:
    """
    Costruisce un documento HTML autosufficiente (CSS incluso inline,
    nessuna risorsa esterna) con la cronologia dei messaggi. Le voci
    vengono mostrate nell'ordine in cui sono passate — il chiamante
    decide l'ordinamento (cronologico, di norma).
    """
    righe_html = []
    for entry in entries:
        allegati_html = ""
        if entry.attachment_filenames:
            lista_allegati = "".join(
                f"<li>{_escape(nome)}</li>" for nome in entry.attachment_filenames
            )
            allegati_html = f'<ul class="attachments">{lista_allegati}</ul>'

        contenuto_html = _escape(entry.content) if entry.content else "<em>(nessun testo)</em>"
        classe_riga = "message deleted-source" if entry.is_deleted_source else "message"

        righe_html.append(
            f"""
            <div class="{classe_riga}">
              <div class="meta">
                <span class="author">{_escape(entry.author_display_name)}</span>
                <span class="tag">({_escape(entry.author_tag)})</span>
                <span class="timestamp">{entry.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}</span>
              </div>
              <div class="content">{contenuto_html}</div>
              {allegati_html}
            </div>
            """
        )

    corpo = "\n".join(righe_html) if righe_html else '<p class="empty">Nessun messaggio indicizzato.</p>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>{_escape(title)}</title>
<style>
  body {{ font-family: -apple-system, sans-serif; background: #313338; color: #dbdee1; padding: 20px; }}
  .header {{ border-bottom: 1px solid #3f4147; padding-bottom: 10px; margin-bottom: 20px; }}
  .header h1 {{ margin: 0; font-size: 20px; }}
  .header .generated {{ color: #949ba4; font-size: 12px; }}
  .message {{ padding: 8px 0; border-bottom: 1px solid #2b2d31; }}
  .message.deleted-source {{ opacity: 0.6; }}
  .meta {{ font-size: 13px; margin-bottom: 4px; }}
  .author {{ font-weight: 600; color: #f2f3f5; }}
  .tag {{ color: #949ba4; margin-left: 4px; }}
  .timestamp {{ color: #949ba4; margin-left: 10px; font-size: 11px; }}
  .content {{ white-space: pre-wrap; word-break: break-word; }}
  .attachments {{ margin: 4px 0 0 0; padding-left: 20px; font-size: 12px; color: #949ba4; }}
  .empty {{ color: #949ba4; font-style: italic; }}
</style>
</head>
<body>
  <div class="header">
    <h1>{_escape(title)}</h1>
    <div class="generated">Generated at {generated_at.strftime('%Y-%m-%d %H:%M:%S UTC')} — {len(entries)} message(s)</div>
  </div>
  {corpo}
</body>
</html>
"""
