"""
core/image_thumbnail_logic.py
================================
Logica pura per la rigenerazione delle thumbnail del transcript
Spam Trap (SPEC.md §7.3, la voce rimasta parziale). Solo decisioni e
costruzione di stringhe qui — l'elaborazione vera dei byte
dell'immagine (Pillow) vive in core/image_thumbnail.py, che questa
logica non tocca, per restare testabile senza generare immagini vere
ad ogni test.

Scelta di design: le thumbnail sono incorporate nell'HTML come data
URI (base64 dentro l'attributo src dell'<img>), non riospitate da
nessuna parte — coerente con l'esigenza originale di "non riospitare
il file originale": qui non lo riospitiamo affatto, il transcript è
un file HTML autosufficiente che porta con sé tutto ciò che gli
serve, senza bisogno di un server immagini a parte.
"""

from __future__ import annotations

import base64

# Estensioni riconosciute come immagine — usate come rete di
# sicurezza quando content_type non è disponibile o è generico
# (es. "application/octet-stream", che alcuni client mandano per
# certi upload). Elenco deliberatamente ristretto ai formati che
# Pillow può aprire senza incertezze.
IMAGE_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"})

# Oltre questa dimensione, l'allegato non viene processato: scaricare
# e decomprimere un'immagine enorme in memoria su una VM con RAM
# limitata è esattamente il tipo di rischio che core/memory_guard.py
# esiste per mitigare — meglio evitarlo alla radice per questo caso
# specifico, dove è prevedibile in anticipo.
MAX_SOURCE_IMAGE_BYTES = 8 * 1024 * 1024  # 8 MB

THUMBNAIL_MAX_DIMENSION = 400  # pixel, lato più lungo


def is_image_attachment(filename: str, content_type: str | None) -> bool:
    """
    True se l'allegato è (quasi sicuramente) un'immagine apribile da
    Pillow. Controlla prima content_type (più affidabile quando
    presente), poi ripiega sull'estensione del nome file.
    """
    if content_type is not None and content_type.startswith("image/"):
        # Le immagini animate via URL tipo image/gif vanno bene;
        # scartiamo esplicitamente le sole eccezioni note che Pillow
        # non apre in modo affidabile senza plugin aggiuntivi.
        if content_type in ("image/svg+xml", "image/heic", "image/heif"):
            return False
        return True

    lower = filename.lower()
    return any(lower.endswith(ext) for ext in IMAGE_EXTENSIONS)


def is_within_size_limit(size_bytes: int) -> bool:
    return size_bytes <= MAX_SOURCE_IMAGE_BYTES


def bytes_to_data_uri(image_bytes: bytes, mime_type: str = "image/webp") -> str:
    encoded = base64.b64encode(image_bytes).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"
